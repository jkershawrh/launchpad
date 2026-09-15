from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from app.services.catalog_certification import (
    build_certification_plan,
    evaluate_json_assertions,
    evaluate_promotion,
    load_certification_contract,
    score_rubric,
    validate_certification_contract,
    write_evidence_bundle,
)
from app.services.catalog_onboarding import load_intake

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "certification/catalog/multi-agent-quickstart.yaml"
INTAKE_PATH = ROOT / "catalog-onboarding/multi-agent-quickstart.yaml"


def _runner_module():
    path = ROOT / "scripts/catalog_certification.py"
    spec = importlib.util.spec_from_file_location("catalog_certification_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multi_agent_is_the_reference_reusable_certification_contract():
    contract = load_certification_contract(CONTRACT_PATH)
    intake = load_intake(INTAKE_PATH)

    assert validate_certification_contract(
        contract,
        intake=intake,
        repo_root=ROOT,
        contract_path=CONTRACT_PATH,
    ) == []
    assert contract["kind"] == "CatalogCertification"
    assert contract["metadata"]["catalog_item_id"] == "multi-agent-quickstart"
    assert contract["spec"]["kubeconfig_server"] == (
        "https://api.arena.fm2aihpcsed.com:6443"
    )
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [
        1,
        5,
        25,
        30,
    ]
    assert intake["certification"]["proof_contract"] == (
        "certification/catalog/multi-agent-quickstart.yaml"
    )


def test_twenty_five_seat_plan_is_one_order_on_one_cluster():
    contract = load_certification_contract(CONTRACT_PATH)
    intake = load_intake(INTAKE_PATH)

    plan = build_certification_plan(
        contract,
        intake=intake,
        seats=25,
        exposure_policy="internal",
    )

    assert plan["catalog_item_id"] == "multi-agent-quickstart"
    assert plan["cluster_ref"] == "arena"
    assert plan["kubeconfig_server"] == "https://api.arena.fm2aihpcsed.com:6443"
    assert plan["workshop_orders"] == 1
    assert plan["seats"] == 25
    assert plan["seat_probe_count"] == 25
    assert plan["all_seats_same_cluster"] is True
    assert plan["provision_concurrency"] == 2
    assert plan["probe_concurrency"] == 10
    assert plan["required_consecutive_runs"] == 3
    assert plan["showroom_pages_per_seat"] == 4
    assert plan["current_certified_seats"] == 25
    assert plan["next_promotion_target"] == 30
    assert plan["execution_eligible"] is True


def test_only_certified_or_next_scale_profile_can_execute():
    contract = load_certification_contract(CONTRACT_PATH)
    intake = load_intake(INTAKE_PATH)

    one = build_certification_plan(
        contract, intake=intake, seats=1, exposure_policy="internal"
    )
    five = build_certification_plan(
        contract, intake=intake, seats=5, exposure_policy="internal"
    )
    twenty_five = build_certification_plan(
        contract, intake=intake, seats=25, exposure_policy="internal"
    )
    thirty = build_certification_plan(
        contract, intake=intake, seats=30, exposure_policy="internal"
    )

    assert one["execution_eligible"] is True
    assert one["certification_override"] is False
    assert five["execution_eligible"] is True
    assert five["certification_override"] is False
    assert twenty_five["execution_eligible"] is True
    assert twenty_five["certification_override"] is False
    assert twenty_five["next_promotion_target"] == 30
    assert thirty["execution_eligible"] is True
    assert thirty["certification_override"] is True
    assert thirty["next_promotion_target"] == 30


def test_contract_rejects_unsafe_or_nonrepeatable_configuration():
    contract = load_certification_contract(CONTRACT_PATH)
    intake = load_intake(INTAKE_PATH)
    broken = deepcopy(contract)
    broken["spec"]["target_cluster"] = ""
    broken["spec"]["scale_profiles"] = [
        broken["spec"]["scale_profiles"][1],
        broken["spec"]["scale_profiles"][0],
    ]
    broken["spec"]["seat_probe"]["argv"] = ["/bin/sh", "-c", "echo unsafe"]
    broken["spec"]["showroom"]["pages"][0]["path"] = "relative/path"

    errors = validate_certification_contract(
        broken,
        intake=intake,
        repo_root=ROOT,
        contract_path=CONTRACT_PATH,
    )

    assert any("target_cluster" in error for error in errors)
    assert any("scale_profiles" in error for error in errors)
    assert any("shell execution" in error for error in errors)
    assert any("absolute URL path" in error for error in errors)


def test_structural_json_assertions_do_not_compare_model_prose():
    contract = load_certification_contract(CONTRACT_PATH)
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    assert assertions[0] == {
        "path": "result",
        "equals": "GREEN-live-internal-seat",
    }
    for expected in (
        {"path": "participant_ui_journey.http_error", "equals": False},
        {"path": "participant_ui_journey.executor_present", "equals": True},
        {"path": "participant_ui_journey.step_count_one", "equals": True},
        {"path": "learner_policy.applied_max_tokens", "equals": 48},
        {"path": "learner_policy.workflow_passed", "equals": True},
        {"path": "learner_policy.rollback_restored_baseline", "equals": True},
        {"path": "learner_policy.configmap_removed", "equals": True},
    ):
        assert expected in assertions
    result = {
        "result": "GREEN-live-internal-seat",
        "cluster_ref": "arena",
        "readiness": {"agents_discovered": 3, "agents_expected": 3},
        "multi_agent_journey": {
            "steps": 3,
            "mcp_steps": ["research", "analyst", "executor"],
            "errors": [],
            "answer": "Nondeterministic model prose is intentionally ignored.",
        },
        "participant_ui_journey": {
            "http_error": False,
            "executor_present": True,
            "step_count_one": True,
        },
        "learner_policy": {
            "applied_max_tokens": 48,
            "workflow_passed": True,
            "rollback_restored_baseline": True,
            "configmap_removed": True,
        },
        "guardrails": {"blocked_steps": ["research", "analyst", "executor"]},
        "terminal_scope": [
            "project=seat-namespace",
            "own_edit=yes",
            "cross_namespace=DENIED",
            "node_list=DENIED",
        ],
        "contains_sensitive_values": False,
    }

    assert evaluate_json_assertions(result, assertions) == []
    result["multi_agent_journey"]["errors"] = ["failed"]
    failures = evaluate_json_assertions(result, assertions)
    assert any("multi_agent_journey.errors" in failure for failure in failures)


def test_rubric_and_promotion_fail_closed_until_every_gate_and_run_passes():
    contract = load_certification_contract(CONTRACT_PATH)
    gates = {
        gate
        for category in contract["spec"]["rubric"]["categories"]
        for gate in category["requires"]
    }
    green = score_rubric(contract, {gate: True for gate in gates})
    red = score_rubric(
        contract,
        {gate: gate != "zero_residue_cleanup" for gate in gates},
    )

    assert green["score"] == green["required"] == 100
    assert green["passed"] is True
    assert red["score"] < 100
    assert red["passed"] is False
    assert evaluate_promotion(contract, seats=25, recent_results=[True, True]) == {
        "required_consecutive_runs": 3,
        "consecutive_passing_runs": 2,
        "eligible": False,
    }
    assert evaluate_promotion(contract, seats=25, recent_results=[True, True, True])[
        "eligible"
    ] is True


def test_evidence_bundle_is_sanitized_and_hashed(tmp_path: Path):
    evidence = {
        "schema": "launchpad.redhat.com/catalog-certification-evidence/v1",
        "result": "GREEN-live",
        "api_key": "must-not-survive",
        "nested": {"access_code": "must-not-survive", "safe": "kept"},
    }
    path = tmp_path / "run.json"

    checksum_path = write_evidence_bundle(path, evidence)
    saved = json.loads(path.read_text())
    expected, filename = checksum_path.read_text().strip().split("  ", maxsplit=1)

    assert saved["api_key"] == "[REDACTED]"
    assert saved["nested"]["access_code"] == "[REDACTED]"
    assert saved["nested"]["safe"] == "kept"
    assert filename == path.name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_evidence_sanitizer_preserves_authorization_rubric_metadata(
    tmp_path: Path,
):
    path = tmp_path / "authorization-rubric.json"

    write_evidence_bundle(
        path,
        {
            "rubric": {
                "categories": {
                    "authorization": {
                        "weight": 15,
                        "awarded": 15,
                        "passed": True,
                    }
                }
            },
            "request": {"authorization": "Bearer do-not-persist"},
        },
    )

    saved = json.loads(path.read_text())
    assert saved["rubric"]["categories"]["authorization"] == {
        "awarded": 15,
        "passed": True,
        "weight": 15,
    }
    assert saved["request"]["authorization"] == "[REDACTED]"


def test_cli_plan_is_machine_readable_and_non_mutating():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/catalog_certification.py"),
            "plan",
            str(CONTRACT_PATH),
            "--intake",
            str(INTAKE_PATH),
            "--seats",
            "25",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    plan = json.loads(result.stdout)
    assert plan["workshop_orders"] == 1
    assert plan["seats"] == 25
    assert plan["cluster_ref"] == "arena"
    assert plan["mutates_cluster"] is False


def test_api_transport_does_not_shadow_the_session_lookup_method():
    runner = _runner_module()

    client = runner.LaunchpadApi("https://launchpad.example", "not-a-real-key")

    assert callable(client.session)


def test_api_transport_recovers_from_connection_loss_and_gateway_unavailability(
    monkeypatch,
):
    runner = _runner_module()
    calls = []

    class Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.ok = 200 <= status_code < 300

        def json(self):
            return self._payload

    client = runner.LaunchpadApi(
        "https://launchpad.example",
        "not-a-real-key",
        transient_retry_seconds=1,
        retry_interval_seconds=0,
    )

    def request(*_args, **_kwargs):
        calls.append("request")
        if len(calls) == 1:
            raise runner.requests.ConnectionError("node disappeared")
        if len(calls) == 2:
            return Response(503, {"detail": "no ready backend endpoint"})
        return Response(200, {"status": "ready"})

    monkeypatch.setattr(client._http, "request", request)

    assert client.workshop("workshop-1") == {"status": "ready"}
    assert calls == ["request", "request", "request"]


def test_cleanup_observation_waits_for_zero_residue(monkeypatch):
    runner = _runner_module()
    snapshots = [
        {"namespaces": 20, "secrets": 40},
        {"namespaces": 0, "secrets": 0},
    ]

    monkeypatch.setattr(
        runner,
        "_resource_counts",
        lambda *_args, **_kwargs: snapshots.pop(0),
    )

    counts, elapsed = runner._wait_for_zero_resources(
        ["namespaces", "secrets"],
        workshop_id="workshop-1",
        kubeconfig="arena-kubeconfig",
        timeout_seconds=1,
        interval_seconds=0,
    )

    assert counts == {"namespaces": 0, "secrets": 0}
    assert snapshots == []
    assert elapsed >= 0


def test_cleanup_observation_uses_control_plane_for_argocd(monkeypatch):
    runner = _runner_module()
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", run)

    counts = runner._resource_counts(
        ["namespaces", "applications.argoproj.io", "secrets"],
        workshop_id="workshop-1",
        kubeconfig="brutus-kubeconfig",
        control_kubeconfig="arena-kubeconfig",
    )

    assert counts == {
        "namespaces": 0,
        "applications.argoproj.io": 0,
        "secrets": 0,
    }
    assert calls[0][2] == "brutus-kubeconfig"
    assert calls[1][2] == "arena-kubeconfig"
    assert calls[2][2] == "brutus-kubeconfig"


def test_failed_seat_probe_preserves_safe_stage_diagnostic(monkeypatch):
    runner = _runner_module()
    contract = load_certification_contract(CONTRACT_PATH)

    monkeypatch.setattr(
        runner,
        "_showroom_checks",
        lambda *_args, **_kwargs: [{"id": "track-chooser", "passed": True}],
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=4,
            stdout="",
            stderr=(
                "transport details that must not be persisted\n"
                "seat_probe_failure stage=semantic-routing exit_code=4\n"
            ),
        ),
    )

    result = runner._seat_probe(
        seat={
            "seat_number": 2,
            "seat_id": "seat-2",
            "session_id": "session-2",
            "showroom_url": "https://showroom.example",
        },
        session={"namespace": "seat-2", "cluster_ref": "arena"},
        contract=contract,
        verify=True,
    )

    assert result["probe"] == {
        "passed": False,
        "exit_code": 4,
        "failure_stage": "semantic-routing",
        "assertion_failures": ["seat probe exited with status 4"],
        "duration_seconds": result["probe"]["duration_seconds"],
    }
    assert "transport details" not in json.dumps(result)


def test_multi_agent_probe_retries_remote_json_and_reports_failure_stage():
    probe = (ROOT / "scripts/certify-multi-agent-seat.sh").read_text()

    assert "oc_exec_json()" in probe
    assert "for attempt in 1 2 3" in probe
    assert probe.count("oc_exec_json orchestrator") == 4
    assert 'seat_probe_failure stage=${stage} exit_code=${rc}' in probe


def test_generic_runner_places_probes_after_the_all_seat_barrier_and_reclaims(
    tmp_path: Path, monkeypatch, capsys
):
    runner = _runner_module()
    calls: list[str] = []
    sessions_fetched: set[str] = set()

    class FakeApi:
        def __init__(self, *_args, **_kwargs):
            pass

        def capacity_preview(self, body):
            calls.append("capacity")
            return {"can_provision": True, "selected_cluster": "arena"}

        def create_order(self, body, *, idempotency_key):
            calls.append("create")
            assert body["num_users"] == 5
            assert body["certification_override"] is False
            assert idempotency_key.endswith(":repeatable-five")
            return {"workshop_id": "workshop-1", "cluster_ref": "arena"}

        def confirm(self, workshop_id):
            calls.append("confirm")
            assert workshop_id == "workshop-1"
            return {"status": "queued"}

        def workshop(self, workshop_id):
            assert workshop_id == "workshop-1"
            if "reclaim" in calls:
                return {"status": "completed", "cluster_ref": "arena", "seats": []}
            return {
                "status": "ready",
                "cluster_ref": "arena",
                "seats": [
                    {
                        "seat_id": f"seat-{seat}",
                        "seat_number": seat,
                        "session_id": f"session-{seat}",
                        "status": "ready",
                        "showroom_url": f"https://seat-{seat}.example",
                    }
                    for seat in range(1, 6)
                ],
            }

        def session(self, session_id):
            sessions_fetched.add(session_id)
            reclaimed = "reclaim" in calls
            return {
                "session_id": session_id,
                "namespace": session_id.replace("session", "namespace"),
                "cluster_ref": "arena",
                "status": "reclaimed" if reclaimed else "ready",
                "maas_api_key": "" if reclaimed else "masked",
            }

        def reclaim(self, workshop_id):
            calls.append("reclaim")
            return {"status": "reclaiming"}

    def fake_seat_probe(*, seat, session, contract, verify):
        assert len(sessions_fetched) == 5
        return {
            "seat_number": seat["seat_number"],
            "showroom": [
                {"id": page["id"], "passed": True}
                for page in contract["spec"]["showroom"]["pages"]
            ],
            "probe": {
                "passed": True,
                "assertion_failures": [],
                "result": {
                    "terminal_scope": [
                        "own_edit=yes",
                        "cross_namespace=DENIED",
                        "node_list=DENIED",
                    ],
                    "contains_sensitive_values": False,
                },
            },
        }

    monkeypatch.setattr(runner, "LaunchpadApi", FakeApi)
    monkeypatch.setattr(runner, "_seat_probe", fake_seat_probe)
    monkeypatch.setattr(
        runner,
        "_kubeconfig_server",
        lambda _kubeconfig: "https://api.arena.fm2aihpcsed.com:6443",
    )
    monkeypatch.setattr(
        runner,
        "_resource_counts",
        lambda resources, **_kwargs: {resource: 0 for resource in resources},
    )
    monkeypatch.setattr(
        runner,
        "_git_value",
        lambda *args: "a" * 40 if args == ("rev-parse", "HEAD") else "",
    )
    monkeypatch.setenv("TEST_LAUNCHPAD_API_KEY", "not-a-real-key")
    monkeypatch.setenv("KUBECONFIG", str(tmp_path / "arena-kubeconfig"))
    output = tmp_path / "evidence" / "five-seat.json"
    args = SimpleNamespace(
        contract=str(CONTRACT_PATH),
        intake=str(INTAKE_PATH),
        seats=5,
        exposure_policy="internal",
        api_key_env="TEST_LAUNCHPAD_API_KEY",
        api_base_url="https://launchpad.example/api/v1",
        tenant_id="certification-tenant",
        owner_id="proof-runner",
        ttl="2h",
        run_id="repeatable-five",
        output=str(output),
        poll_interval=0.001,
        ca_bundle=None,
        insecure=False,
        allow_dirty=True,
    )

    assert runner._run_command(args) == 0
    evidence = json.loads(output.read_text())

    assert calls == ["capacity", "create", "confirm", "reclaim"]
    assert len(evidence["seat_results"]) == 5
    assert evidence["result"] == "GREEN-live"
    assert evidence["rubric"]["score"] == 100
    assert evidence["cleanup"]["status"] == "completed"
    assert set(evidence["proof_strategy"]) == {"TDD", "EDD", "CDD", "BDD", "CBT"}
    assert all(
        status == "GREEN-live" for status in evidence["validation_matrix"].values()
    )
    assert all(count == 0 for count in evidence["cleanup"]["resource_counts"].values())
    assert output.with_name(output.name + ".sha256").is_file()
    assert "not-a-real-key" not in capsys.readouterr().out
