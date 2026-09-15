#!/usr/bin/env python3
"""Plan and execute repeatable, evidence-producing catalog certification runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.catalog_certification import (
    build_certification_plan,
    evaluate_json_assertions,
    evaluate_promotion,
    load_certification_contract,
    sanitize_evidence,
    score_rubric,
    validate_certification_contract,
    write_evidence_bundle,
)
from app.services.catalog_onboarding import load_intake

TERMINAL_WORKSHOP_STATUSES = {"ready", "active", "partially_ready", "failed"}
TERMINAL_CLEANUP_STATUSES = {"completed", "cleanup_failed"}
CLUSTER_SCOPED_RESOURCES = {"namespaces", "persistentvolumes"}
CONTROL_PLANE_RESOURCES = {"applications.argoproj.io"}
PROBE_FAILURE_STAGE = re.compile(
    r"(?:^|\s)seat_probe_failure stage=([a-z0-9-]+) exit_code=\d+(?:\s|$)"
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _contract_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _kubeconfig_server(kubeconfig: str) -> str:
    result = subprocess.run(
        [
            "oc",
            "--kubeconfig",
            kubeconfig,
            "config",
            "view",
            "--minify",
            "--output",
            "jsonpath={.clusters[0].cluster.server}",
        ],
        check=True,
        text=True,
        capture_output=True,
        timeout=30,
    )
    return result.stdout.strip()


class LaunchpadApi:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        verify: bool | str = True,
        transient_retry_seconds: float = 300,
        retry_interval_seconds: float = 5,
    ):
        root = base_url.rstrip("/")
        self.base_url = root if root.endswith("/api/v1") else f"{root}/api/v1"
        self.verify = verify
        self.transient_retry_seconds = max(0, transient_retry_seconds)
        self.retry_interval_seconds = max(0, retry_interval_seconds)
        self._http = requests.Session()
        self._http.headers.update({"X-API-Key": api_key})

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        request_timeout = float(kwargs.pop("timeout", 60))
        retry_deadline = time.monotonic() + self.transient_retry_seconds
        while True:
            remaining = retry_deadline - time.monotonic()
            try:
                response = self._http.request(
                    method,
                    f"{self.base_url}{path}",
                    timeout=min(request_timeout, max(1, remaining)),
                    verify=self.verify,
                    **kwargs,
                )
            except requests.RequestException:
                if time.monotonic() >= retry_deadline:
                    raise
                time.sleep(min(self.retry_interval_seconds, max(0, remaining)))
                continue
            if response.status_code in {502, 503, 504}:
                if time.monotonic() >= retry_deadline:
                    break
                time.sleep(min(self.retry_interval_seconds, max(0, remaining)))
                continue
            break
        if not response.ok:
            try:
                detail = response.json().get("detail", "request failed")
            except (ValueError, AttributeError):
                detail = "request failed"
            raise RuntimeError(
                f"Launchpad API {method} {path} returned {response.status_code}: {detail}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError(f"Launchpad API {method} {path} returned a non-object")
        return payload

    def capacity_preview(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/workshops/capacity-preview", json=body)

    def create_order(
        self, body: dict[str, Any], *, idempotency_key: str
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/workshops/orders",
            json=body,
            headers={"Idempotency-Key": idempotency_key},
        )

    def confirm(self, workshop_id: str) -> dict[str, Any]:
        return self.request("POST", f"/workshops/{workshop_id}/confirm")

    def workshop(self, workshop_id: str) -> dict[str, Any]:
        return self.request("GET", f"/workshops/{workshop_id}")

    def session(self, session_id: str) -> dict[str, Any]:
        return self.request("GET", f"/lab-sessions/{session_id}")

    def reclaim(self, workshop_id: str) -> dict[str, Any]:
        return self.request("DELETE", f"/workshops/{workshop_id}")


def _wait_for_status(
    fetch,
    *,
    terminal: set[str],
    timeout_seconds: int,
    interval_seconds: float,
) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    while True:
        payload = fetch()
        if payload.get("status") in terminal:
            return payload, time.monotonic() - started
        if time.monotonic() - started >= timeout_seconds:
            raise TimeoutError(
                f"Timed out after {timeout_seconds}s waiting for {sorted(terminal)}"
            )
        time.sleep(interval_seconds)


def _format_probe_argv(
    argv: list[str], *, namespace: str, cluster_ref: str, seat_number: int
) -> list[str]:
    values = {
        "namespace": namespace,
        "cluster_ref": cluster_ref,
        "seat_number": str(seat_number),
    }
    return [argument.format(**values) for argument in argv]


def _showroom_checks(
    base_url: str,
    pages: list[dict[str, Any]],
    *,
    verify: bool | str,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for page in pages:
        started = time.monotonic()
        try:
            response = requests.get(
                f"{base_url.rstrip('/')}{page['path']}",
                timeout=30,
                verify=verify,
            )
            marker_present = page["marker"] in response.text
            passed = response.status_code == 200 and marker_present
            checks.append(
                {
                    "id": page["id"],
                    "track_id": page.get("track_id"),
                    "http_status": response.status_code,
                    "marker_present": marker_present,
                    "passed": passed,
                    "duration_seconds": round(time.monotonic() - started, 3),
                }
            )
        except requests.RequestException as exc:
            checks.append(
                {
                    "id": page["id"],
                    "track_id": page.get("track_id"),
                    "http_status": None,
                    "marker_present": False,
                    "passed": False,
                    "error": type(exc).__name__,
                    "duration_seconds": round(time.monotonic() - started, 3),
                }
            )
    return checks


def _seat_probe(
    *,
    seat: dict[str, Any],
    session: dict[str, Any],
    contract: dict[str, Any],
    verify: bool | str,
) -> dict[str, Any]:
    spec = contract["spec"]
    namespace = str(session.get("namespace") or seat.get("namespace") or "")
    seat_number = int(seat["seat_number"])
    showroom_url = str(
        seat.get("showroom_url")
        or session.get("resources", {}).get("showroom_url")
        or seat.get("lab_url")
        or session.get("lab_url")
        or ""
    )
    result: dict[str, Any] = {
        "seat_number": seat_number,
        "seat_id": seat.get("seat_id"),
        "session_id": seat.get("session_id"),
        "namespace": namespace,
        "cluster_ref": session.get("cluster_ref"),
        "showroom": [],
        "probe": {"passed": False, "assertion_failures": []},
    }
    if not namespace or not showroom_url:
        result["error"] = "seat is missing namespace or Showroom URL"
        return result

    result["showroom"] = _showroom_checks(
        showroom_url,
        spec["showroom"]["pages"],
        verify=verify,
    )
    probe = spec["seat_probe"]
    argv = _format_probe_argv(
        probe["argv"],
        namespace=namespace,
        cluster_ref=spec["target_cluster"],
        seat_number=seat_number,
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            env=os.environ.copy(),
            check=False,
            text=True,
            capture_output=True,
            timeout=probe["timeout_seconds"],
        )
        if completed.returncode != 0:
            failed_probe = {
                "passed": False,
                "exit_code": completed.returncode,
                "assertion_failures": [
                    f"seat probe exited with status {completed.returncode}"
                ],
                "duration_seconds": round(time.monotonic() - started, 3),
            }
            stages = PROBE_FAILURE_STAGE.findall(completed.stderr or "")
            if stages:
                failed_probe["failure_stage"] = stages[-1]
            result["probe"] = failed_probe
            return result
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result["probe"] = {
                "passed": False,
                "exit_code": completed.returncode,
                "assertion_failures": ["seat probe did not return one JSON object"],
                "duration_seconds": round(time.monotonic() - started, 3),
            }
            return result
        failures = evaluate_json_assertions(payload, probe["json_assertions"])
        result["probe"] = {
            "passed": not failures,
            "exit_code": completed.returncode,
            "assertion_failures": failures,
            "duration_seconds": round(time.monotonic() - started, 3),
            "result": sanitize_evidence(payload),
        }
    except subprocess.TimeoutExpired:
        result["probe"] = {
            "passed": False,
            "exit_code": None,
            "assertion_failures": [
                f"seat probe exceeded {probe['timeout_seconds']} seconds"
            ],
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    return result


def _resource_counts(
    resources: list[str],
    *,
    workshop_id: str,
    kubeconfig: str,
    cleanup_kubeconfig: str | None = None,
    control_kubeconfig: str | None = None,
) -> dict[str, int]:
    selector = f"launchpad.redhat.com/workshop-id={workshop_id}"
    counts: dict[str, int] = {}
    for resource in resources:
        resource_kubeconfig = cleanup_kubeconfig or kubeconfig
        if resource in CONTROL_PLANE_RESOURCES and control_kubeconfig:
            resource_kubeconfig = control_kubeconfig
        command = [
            "oc",
            "--kubeconfig",
            resource_kubeconfig,
            "get",
            resource,
        ]
        if resource not in CLUSTER_SCOPED_RESOURCES:
            command.append("--all-namespaces")
        command.extend(["--selector", selector, "--output", "name"])
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if completed.returncode != 0:
            counts[resource] = -1
        else:
            counts[resource] = len(
                [line for line in completed.stdout.splitlines() if line.strip()]
            )
    return counts


def _wait_for_zero_resources(
    resources: list[str],
    *,
    workshop_id: str,
    kubeconfig: str,
    cleanup_kubeconfig: str | None = None,
    control_kubeconfig: str | None = None,
    timeout_seconds: float,
    interval_seconds: float,
) -> tuple[dict[str, int], float]:
    """Wait for asynchronous namespace garbage collection within the cleanup SLO."""
    started = time.monotonic()
    while True:
        counts = _resource_counts(
            resources,
            workshop_id=workshop_id,
            kubeconfig=kubeconfig,
            cleanup_kubeconfig=cleanup_kubeconfig,
            control_kubeconfig=control_kubeconfig,
        )
        elapsed = time.monotonic() - started
        if counts and all(count == 0 for count in counts.values()):
            return counts, elapsed
        if elapsed >= timeout_seconds:
            return counts, elapsed
        time.sleep(interval_seconds)


def _load_history(
    directory: Path,
    *,
    catalog_item_id: str,
    seats: int,
    contract_sha256: str,
) -> list[bool]:
    records: list[tuple[str, bool]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("schema") != "launchpad.redhat.com/catalog-certification-evidence/v1":
            continue
        if payload.get("catalog_item_id") != catalog_item_id:
            continue
        if payload.get("plan", {}).get("seats") != seats:
            continue
        if payload.get("contract", {}).get("sha256") != contract_sha256:
            continue
        records.append(
            (
                str(payload.get("completed_at", "")),
                payload.get("result") == "GREEN-live",
            )
        )
    return [result for _, result in sorted(records)]


def _validate_inputs(
    contract_path: Path, intake_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_certification_contract(contract_path)
    intake = load_intake(intake_path)
    errors = validate_certification_contract(
        contract,
        intake=intake,
        repo_root=REPO_ROOT,
        contract_path=contract_path,
    )
    if errors:
        raise ValueError("Invalid certification contract: " + "; ".join(errors))
    return contract, intake


def _default_intake(contract: dict[str, Any]) -> Path:
    return REPO_ROOT / "catalog-onboarding" / (
        f"{contract['metadata']['catalog_item_id']}.yaml"
    )


def _resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    contract_path = Path(args.contract).resolve()
    contract = load_certification_contract(contract_path)
    intake_path = (
        Path(args.intake).resolve() if args.intake else _default_intake(contract)
    )
    contract, intake = _validate_inputs(contract_path, intake_path)
    return contract_path, intake_path, contract, intake


def _validate_command(args: argparse.Namespace) -> int:
    contract_path, intake_path, contract, _ = _resolve_inputs(args)
    print(
        json.dumps(
            {
                "validation_status": "pass",
                "catalog_item_id": contract["metadata"]["catalog_item_id"],
                "contract": str(contract_path.relative_to(REPO_ROOT)),
                "intake": str(intake_path.relative_to(REPO_ROOT)),
            },
            indent=2,
        )
    )
    return 0


def _plan_command(args: argparse.Namespace) -> int:
    _, _, contract, intake = _resolve_inputs(args)
    plan = build_certification_plan(
        contract,
        intake=intake,
        seats=args.seats,
        exposure_policy=args.exposure_policy,
    )
    print(json.dumps(plan, indent=2))
    return 0


def _run_command(args: argparse.Namespace) -> int:
    contract_path, intake_path, contract, intake = _resolve_inputs(args)
    plan = build_certification_plan(
        contract,
        intake=intake,
        seats=args.seats,
        exposure_policy=args.exposure_policy,
    )
    if not plan["execution_eligible"]:
        raise ValueError(
            f"{args.seats} seats cannot run before the "
            f"{plan['next_promotion_target']}-seat promotion gate passes"
        )
    plan["mutates_cluster"] = True
    api_key = os.environ.get(args.api_key_env, "")
    kubeconfig = os.environ.get("KUBECONFIG", "")
    cleanup_kubeconfig = getattr(args, "cleanup_kubeconfig", None) or kubeconfig
    control_kubeconfig = getattr(args, "control_kubeconfig", None) or kubeconfig
    if not api_key:
        raise ValueError(f"{args.api_key_env} must contain the Launchpad API credential")
    if not kubeconfig:
        raise ValueError("KUBECONFIG must point to the target execution cluster credential")
    actual_server = _kubeconfig_server(kubeconfig)
    if actual_server != plan["kubeconfig_server"]:
        raise ValueError(
            f"KUBECONFIG targets {actual_server!r}; expected {plan['kubeconfig_server']!r}"
        )

    tracked_changes = _git_value("status", "--porcelain", "--untracked-files=no")
    if tracked_changes and not args.allow_dirty:
        raise ValueError(
            "Tracked repository files are dirty; commit the proof contract before a live run"
        )

    verify: bool | str = True
    if args.insecure:
        verify = False
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    elif args.ca_bundle:
        verify = str(Path(args.ca_bundle).resolve())

    api = LaunchpadApi(args.api_base_url, api_key, verify=verify)
    run_id = args.run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    contract_sha256 = _contract_hash(contract_path)
    profile = next(
        profile
        for profile in contract["spec"]["scale_profiles"]
        if profile["seats"] == args.seats
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else REPO_ROOT
        / "evidence/runs"
        / f"{plan['catalog_item_id']}-{args.seats}-seat-{run_id}.json"
    )
    body = {
        "tenant_id": args.tenant_id,
        "catalog_item_id": plan["catalog_item_id"],
        "num_users": args.seats,
        "name": f"Certification {run_id}",
        "owner_id": args.owner_id,
        "ttl": args.ttl,
        "purpose": "certification",
        "target_cluster": plan["cluster_ref"],
        "certification_override": plan["certification_override"],
        "exposure_policy": args.exposure_policy,
    }

    started_at = _utc_now()
    errors: list[str] = []
    capacity: dict[str, Any] = {}
    workshop: dict[str, Any] = {}
    sessions: list[dict[str, Any]] = []
    seat_results: list[dict[str, Any]] = []
    ready_seconds: float | None = None
    cleanup_seconds: float | None = None
    cleanup_status = "not-started"
    cleanup_counts = {resource: -1 for resource in contract["spec"]["cleanup"]["resources"]}
    model_keys_revoked = False
    workshop_id = ""

    try:
        capacity = api.capacity_preview(body)
        if not capacity.get("can_provision"):
            raise RuntimeError(f"Capacity preview rejected the run: {capacity.get('reason')}")
        if capacity.get("selected_cluster") != plan["cluster_ref"]:
            raise RuntimeError("Capacity preview selected a different cluster")

        workshop = api.create_order(
            body,
            idempotency_key=f"catalog-certification:{plan['catalog_item_id']}:{run_id}",
        )
        workshop_id = str(workshop["workshop_id"])
        if workshop.get("cluster_ref") != plan["cluster_ref"]:
            raise RuntimeError("Workshop persisted a different cluster_ref")
        api.confirm(workshop_id)
        workshop, ready_seconds = _wait_for_status(
            lambda: api.workshop(workshop_id),
            terminal=TERMINAL_WORKSHOP_STATUSES,
            timeout_seconds=profile["maximum_ready_seconds"],
            interval_seconds=args.poll_interval,
        )
        ready_seats = [
            seat for seat in workshop.get("seats", []) if seat.get("status") == "ready"
        ]
        if workshop.get("status") not in {"ready", "active"}:
            raise RuntimeError(f"Workshop stopped in {workshop.get('status')} state")
        if len(ready_seats) != args.seats:
            raise RuntimeError(f"Only {len(ready_seats)} of {args.seats} seats became ready")

        for seat in ready_seats:
            session = api.session(str(seat["session_id"]))
            if session.get("cluster_ref") != plan["cluster_ref"]:
                raise RuntimeError(
                    f"Seat {seat['seat_number']} persisted a different cluster_ref"
                )
            sessions.append(session)

        # Every seat is ready before any functional workload starts. The
        # executor then supplies a bounded, simultaneous participant load.
        with ThreadPoolExecutor(max_workers=profile["probe_concurrency"]) as executor:
            futures = {
                executor.submit(
                    _seat_probe,
                    seat=seat,
                    session=session,
                    contract=contract,
                    verify=verify,
                ): int(seat["seat_number"])
                for seat, session in zip(ready_seats, sessions, strict=True)
            }
            for future in as_completed(futures):
                seat_number = futures[future]
                try:
                    seat_results.append(future.result())
                # A third-party lab probe may raise any Python exception. Keep
                # the other seat results and, most importantly, reach reclaim.
                except Exception as exc:  # noqa: BLE001
                    seat_results.append(
                        {
                            "seat_number": seat_number,
                            "showroom": [],
                            "probe": {"passed": False, "assertion_failures": []},
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        seat_results.sort(key=lambda item: item["seat_number"])
    # Evidence and cleanup must survive failures from APIs, subprocesses, and
    # future lab-specific probes, including exception types not known here.
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        if workshop_id:
            try:
                api.reclaim(workshop_id)
                reclaimed, cleanup_seconds = _wait_for_status(
                    lambda: api.workshop(workshop_id),
                    terminal=TERMINAL_CLEANUP_STATUSES,
                    timeout_seconds=profile["maximum_cleanup_seconds"],
                    interval_seconds=args.poll_interval,
                )
                cleanup_status = str(reclaimed.get("status"))
            except Exception as exc:  # noqa: BLE001 - preserve evidence on cleanup defects
                errors.append(f"cleanup {type(exc).__name__}: {exc}")
                cleanup_status = "error"
            remaining_cleanup_seconds = max(
                0,
                profile["maximum_cleanup_seconds"] - (cleanup_seconds or 0),
            )
            cleanup_counts, residue_seconds = _wait_for_zero_resources(
                contract["spec"]["cleanup"]["resources"],
                workshop_id=workshop_id,
                kubeconfig=kubeconfig,
                cleanup_kubeconfig=cleanup_kubeconfig,
                control_kubeconfig=control_kubeconfig,
                timeout_seconds=remaining_cleanup_seconds,
                interval_seconds=args.poll_interval,
            )
            cleanup_seconds = (cleanup_seconds or 0) + residue_seconds
            try:
                final_sessions = [
                    api.session(str(session["session_id"])) for session in sessions
                ]
                model_keys_revoked = bool(final_sessions) and all(
                    final.get("status") == "reclaimed"
                    and not final.get("maas_api_key")
                    for final in final_sessions
                )
            except Exception as exc:  # noqa: BLE001 - cleanup proof must fail closed
                errors.append(f"session cleanup {type(exc).__name__}: {exc}")

    all_seats_ready = (
        workshop.get("status") in {"ready", "active"}
        and len(workshop.get("seats", [])) == args.seats
        and all(seat.get("status") == "ready" for seat in workshop.get("seats", []))
    )
    showroom_pages_passed = len(seat_results) == args.seats and all(
        len(result.get("showroom", [])) == len(contract["spec"]["showroom"]["pages"])
        and all(check.get("passed") for check in result["showroom"])
        for result in seat_results
    )
    seat_probes_passed = len(seat_results) == args.seats and all(
        result.get("probe", {}).get("passed") for result in seat_results
    )
    namespace_isolation_passed = seat_probes_passed and all(
        "cross_namespace=DENIED" in result["probe"]["result"].get("terminal_scope", [])
        and "node_list=DENIED" in result["probe"]["result"].get("terminal_scope", [])
        for result in seat_results
    )
    sensitive_values_absent = seat_probes_passed and all(
        result["probe"]["result"].get("contains_sensitive_values") is False
        for result in seat_results
    )
    zero_residue = bool(cleanup_counts) and all(
        count == 0 for count in cleanup_counts.values()
    )
    gates = {
        "contract_valid": True,
        "evidence_hashed": True,
        "capacity_passed": capacity.get("can_provision") is True,
        "single_cluster_assignment": bool(workshop_id)
        and workshop.get("cluster_ref") == plan["cluster_ref"]
        and all(session.get("cluster_ref") == plan["cluster_ref"] for session in sessions),
        "all_seats_ready": all_seats_ready,
        "ready_within_limit": ready_seconds is not None
        and ready_seconds <= profile["maximum_ready_seconds"],
        "showroom_pages_passed": showroom_pages_passed,
        "seat_probes_passed": seat_probes_passed,
        "namespace_isolation_passed": namespace_isolation_passed,
        "sensitive_values_absent": sensitive_values_absent,
        "cleanup_completed": cleanup_status == "completed",
        "zero_residue_cleanup": zero_residue,
        "model_keys_revoked": model_keys_revoked,
    }
    rubric = score_rubric(contract, gates)
    result = "GREEN-live" if rubric["passed"] and not errors else "RED-live"
    history = _load_history(
        output.parent,
        catalog_item_id=plan["catalog_item_id"],
        seats=args.seats,
        contract_sha256=contract_sha256,
    )
    history.append(result == "GREEN-live")
    promotion = evaluate_promotion(contract, seats=args.seats, recent_results=history)
    completed_at = _utc_now()
    evidence = {
        "schema": "launchpad.redhat.com/catalog-certification-evidence/v1",
        "run_id": run_id,
        "catalog_item_id": plan["catalog_item_id"],
        "result": result,
        "started_at": started_at,
        "completed_at": completed_at,
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": contract_sha256,
            "intake_path": str(intake_path.relative_to(REPO_ROOT)),
            "catalog_version": intake["catalog"]["version"],
            "git_commit": _git_value("rev-parse", "HEAD"),
        },
        "plan": plan,
        "capacity_preview": capacity,
        "order": {
            "workshop_id": workshop_id or None,
            "cluster_ref": workshop.get("cluster_ref"),
            "status_before_reclaim": workshop.get("status"),
            "seat_count": args.seats,
            "ready_seconds": round(ready_seconds, 3) if ready_seconds is not None else None,
            "session_ids": [session.get("session_id") for session in sessions],
            "namespaces": [session.get("namespace") for session in sessions],
        },
        "seat_results": seat_results,
        "cleanup": {
            "status": cleanup_status,
            "seconds": round(cleanup_seconds, 3) if cleanup_seconds is not None else None,
            "resource_counts": cleanup_counts,
            "model_keys_revoked": model_keys_revoked,
        },
        "gates": gates,
        "validation_matrix": {
            gate: "GREEN-live" if passed else "RED-live"
            for gate, passed in gates.items()
        },
        "rubric": rubric,
        "promotion": promotion,
        "proof_strategy": {
            "TDD": "Contract, planner, assertion, runner, cleanup, and evidence behavior are protected by failing-then-passing tests.",
            "EDD": "The run writes immutable source identity, lifecycle timing, per-seat results, cleanup counts, rubric decisions, and a SHA-256 manifest.",
            "CDD": "The versioned CatalogCertification document defines scale, Showroom, probe, cleanup, and promotion interfaces.",
            "BDD": "Given one workshop order, all seats must become ready before concurrent participant journeys run, and reclaim must leave zero residue.",
            "CBT": "Contract parsing, API lifecycle, Showroom checks, lab-specific probes, isolation, rubric scoring, and cleanup are independently observable components.",
        },
        "errors": errors,
        "security": {
            "contains_plaintext_credentials": False,
            "credential_values_logged": False,
        },
    }
    checksum_path = write_evidence_bundle(output, evidence)
    print(
        json.dumps(
            {
                "result": result,
                "evidence": str(output),
                "checksum": str(checksum_path),
                "rubric": rubric["score"],
                "promotion": promotion,
            },
            indent=2,
        )
    )
    return 0 if result == "GREEN-live" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("validate", "plan"):
        command = subparsers.add_parser(name)
        command.add_argument("contract")
        command.add_argument("--intake")
        if name == "plan":
            command.add_argument("--seats", type=int, required=True)
            command.add_argument(
                "--exposure-policy",
                choices=("internal", "public_code"),
                default="internal",
            )

    run = subparsers.add_parser("run")
    run.add_argument("contract")
    run.add_argument("--intake")
    run.add_argument("--seats", type=int, required=True)
    run.add_argument("--api-base-url", required=True)
    run.add_argument("--api-key-env", default="LAUNCHPAD_ADMIN_API_KEY")
    run.add_argument("--tenant-id", required=True)
    run.add_argument("--owner-id", required=True)
    run.add_argument("--ttl", default="4h")
    run.add_argument("--run-id")
    run.add_argument("--output")
    run.add_argument("--poll-interval", type=float, default=5.0)
    run.add_argument("--ca-bundle")
    run.add_argument(
        "--cleanup-kubeconfig",
        help=(
            "Read-only observer kubeconfig for execution-cluster residue checks; "
            "defaults to KUBECONFIG"
        ),
    )
    run.add_argument(
        "--control-kubeconfig",
        help=(
            "Kubeconfig for centralized control-plane resources such as Argo CD "
            "Applications; defaults to KUBECONFIG"
        ),
    )
    run.add_argument("--insecure", action="store_true")
    run.add_argument("--allow-dirty", action="store_true")
    run.add_argument(
        "--exposure-policy",
        choices=("internal", "public_code"),
        default="internal",
    )
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        if args.command == "validate":
            return _validate_command(args)
        if args.command == "plan":
            return _plan_command(args)
        return _run_command(args)
    except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f"catalog certification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
