from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy/launchpad/overlays/flightpath-candidate-04-rollback"


def _documents() -> list[dict]:
    result = subprocess.run(
        ["oc", "kustomize", str(OVERLAY)],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _deployment(documents: list[dict], name: str) -> dict:
    matches = [
        doc
        for doc in documents
        if doc.get("kind") == "Deployment" and doc.get("metadata", {}).get("name") == name
    ]
    assert len(matches) == 1
    return matches[0]


def test_rollback_preserves_candidate_shape_and_reverts_runtime_images() -> None:
    documents = _documents()
    backend = _deployment(documents, "backend")
    backend_spec = backend["spec"]["template"]["spec"]
    volumes = {volume["name"] for volume in backend_spec["volumes"]}
    mounts = {
        mount["name"]
        for container in backend_spec["containers"]
        for mount in container.get("volumeMounts", [])
    }

    assert mounts <= volumes
    assert "candidate-agent-reliability-catalog" in volumes
    assert "canonical-ai-sandbox-catalog" in volumes
    assert backend_spec["containers"][0]["image"] == (
        "quay.io/rh-ee-jkershaw/launchpad-backend@"
        "sha256:e922ef53a5e08ae957de8b0a034652f7d64d605e09bdc032a6405279ba9c16e1"
    )

    portal = _deployment(documents, "partner-portal")
    assert portal["spec"]["template"]["spec"]["containers"][0]["image"] == (
        "quay.io/rh-ee-jkershaw/launchpad-portal@"
        "sha256:84358765ab9c78258fbba8ddb50791dcff69578b7c2fc6a822758d25c4b7f71d"
    )

    admin = _deployment(documents, "admin")
    assert admin["spec"]["template"]["spec"]["containers"][0]["image"] == (
        "quay.io/rh-ee-jkershaw/launchpad-admin@"
        "sha256:b599a1d7b75005c55ce32fbe51db86d1aa3e8c0946260d0310dfa700f55acb29"
    )
