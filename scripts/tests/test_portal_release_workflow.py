from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/portal-release.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def test_portal_release_is_manual_and_publish_defaults_off() -> None:
    workflow = _workflow()
    dispatch = workflow[True]["workflow_dispatch"]["inputs"]

    assert dispatch["expected_sha"]["required"] is True
    assert dispatch["publish"]["required"] is True
    assert dispatch["publish"]["default"] is False


def test_portal_release_covers_requester_and_admin_at_exact_revision() -> None:
    text = WORKFLOW.read_text()
    workflow = _workflow()
    includes = workflow["jobs"]["release"]["strategy"]["matrix"]["include"]

    assert {entry["component"] for entry in includes} == {"requester", "admin"}
    assert {entry["containerfile"] for entry in includes} == {
        "frontend/Containerfile",
        "admin/Containerfile",
    }
    assert "test \"${{ github.sha }}\" = \"${{ inputs.expected_sha }}\"" in text
    assert "platforms: linux/amd64" in text


def test_portal_release_scans_sboms_signs_and_attests() -> None:
    text = WORKFLOW.read_text()

    assert "anchore/scan-action@" in text
    assert "severity-cutoff: high" in text
    assert "anchore/sbom-action@" in text
    assert "cosign sign --yes" in text
    assert "actions/attest-build-provenance@" in text
    assert "LAUNCHPAD_QUAY_TOKEN" in text


def test_ci_builds_both_portal_containerfiles() -> None:
    text = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "-f frontend/Containerfile frontend/" in text
    assert "-f admin/Containerfile admin/" in text
