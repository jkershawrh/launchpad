#!/usr/bin/env python3
"""Validate and optionally render a Flightpath promotion bundle without cluster access."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST_IMAGE = re.compile(r"^[^\s]+@sha256:[0-9a-f]{64}$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _git(root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=False, text=text
    )


def _candidate(root: Path, relative_path: str) -> dict[str, Any]:
    path = (root / relative_path).resolve()
    _require(root.resolve() in path.parents, "candidate path escapes repository")
    _require(path.is_file(), f"candidate does not exist: {relative_path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate(bundle: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    _require(
        bundle.get("schema_version")
        == "launchpad.redhat.com/staging-promotion-bundle/v1",
        "unsupported bundle schema",
    )
    target = bundle.get("target") or {}
    _require(target.get("cluster_id") == "flightpath", "target must be Flightpath")
    _require(
        target.get("api_server") == "https://api.flightpath.fm2aihpcsed.com:6443",
        "unexpected Flightpath API server",
    )
    _require(target.get("public_traffic") == "disabled", "public traffic must stay disabled")

    identities: dict[str, Any] = {}
    for action in ("promotion", "rollback"):
        release = bundle.get(action) or {}
        revision = release.get("revision", "")
        _require(bool(SHA.fullmatch(revision)), f"{action} revision must be a full Git SHA")
        resolved = _git(root, "cat-file", "-e", f"{revision}^{{commit}}")
        _require(resolved.returncode == 0, f"{action} revision does not resolve")
        overlay_path = release.get("overlay_path", "")
        _require(not Path(overlay_path).is_absolute(), f"{action} overlay path must be relative")
        tree = _git(root, "cat-file", "-e", f"{revision}:{overlay_path}/kustomization.yaml")
        _require(tree.returncode == 0, f"{action} overlay is absent from pinned revision")
        expected_hash = release.get("rendered_sha256", "")
        _require(
            bool(re.fullmatch(r"[0-9a-f]{64}", expected_hash)),
            f"{action} rendered hash is invalid",
        )
        _require(
            bool(DIGEST_IMAGE.fullmatch(release.get("backend_image", ""))),
            f"{action} backend image must be digest pinned",
        )
        candidate = _candidate(root, release.get("candidate_path", ""))
        _require(candidate.get("candidate_id") == release.get("candidate_id"), f"{action} candidate id drift")
        _require(
            candidate.get("platform", {}).get("revision") == revision,
            f"{action} candidate revision drift",
        )
        identities[action] = {"candidate_id": release["candidate_id"], "revision": revision}

    _require(
        bundle["rollback"].get("database_restore")
        == "forbidden-without-separately-verified-compatible-backup",
        "rollback must fail closed for database restore",
    )
    gates = bundle.get("gates") or {}
    for gate in (
        "approval_required",
        "dry_run_required",
        "exact_api_server_required",
        "secrets_preexist_out_of_band",
        "retained_workshops_must_be_zero",
        "database_backup_required",
        "rollback_decision_owner_required",
    ):
        _require(gates.get(gate) is True, f"required gate is not enabled: {gate}")
    _require(gates.get("public_tls_gate") == "blocked", "public TLS gate must remain blocked")
    return {"valid": True, "bundle_id": bundle["bundle_id"], "identities": identities}


def render(bundle: dict[str, Any], action: str, *, root: Path = ROOT) -> bytes:
    release = bundle[action]
    version = subprocess.run(
        ["oc", "version", "--client", "-o", "json"],
        capture_output=True,
        check=False,
        text=True,
    )
    _require(version.returncode == 0, "cannot determine oc kustomize version")
    observed_version = json.loads(version.stdout).get("kustomizeVersion")
    _require(
        observed_version == bundle.get("render", {}).get("kustomize_version"),
        "oc kustomize version does not match bundle",
    )
    with tempfile.TemporaryDirectory(prefix="flightpath-bundle-") as directory:
        archive = _git(root, "archive", release["revision"], text=False)
        _require(archive.returncode == 0, f"cannot archive {action} revision")
        archive_path = Path(directory) / "source.tar"
        archive_path.write_bytes(archive.stdout)
        with tarfile.open(archive_path) as source:
            members = source.getmembers()
            _require(
                all(
                    not Path(member.name).is_absolute()
                    and ".." not in Path(member.name).parts
                    for member in members
                ),
                f"{action} archive contains an unsafe path",
            )
            source.extractall(directory, members=members)
        rendered = subprocess.run(
            ["oc", "kustomize", str(Path(directory) / release["overlay_path"])],
            capture_output=True,
            check=False,
        )
        _require(rendered.returncode == 0, f"{action} render failed")
        actual = hashlib.sha256(rendered.stdout).hexdigest()
        _require(actual == release["rendered_sha256"], f"{action} rendered hash drift")
        return rendered.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--render", choices=("promotion", "rollback"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    bundle = yaml.safe_load(args.bundle.read_text(encoding="utf-8"))
    report = validate(bundle)
    if args.render:
        payload = render(bundle, args.render)
        _require(args.output is not None, "--output is required with --render")
        args.output.write_bytes(payload)
        report["rendered"] = args.render
        report["output"] = str(args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
