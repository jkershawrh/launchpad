from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/backend-release.yml"


def _workflow() -> tuple[str, dict]:
    text = WORKFLOW.read_text()
    return text, yaml.safe_load(text)


def test_backend_release_is_manual_and_publish_defaults_off() -> None:
    _, workflow = _workflow()
    dispatch = workflow[True]["workflow_dispatch"]["inputs"]

    assert dispatch["expected_sha"]["required"] is True
    assert dispatch["publish"]["default"] is False
    assert dispatch["publish"]["type"] == "boolean"


def test_backend_release_binds_build_to_exact_revision_and_linux_amd64() -> None:
    text, _ = _workflow()

    assert 'test "${{ github.sha }}" = "${{ inputs.expected_sha }}"' in text
    assert 'test "$(git rev-parse HEAD)" = "${{ inputs.expected_sha }}"' in text
    assert "platforms: linux/amd64" in text
    assert "org.opencontainers.image.revision=${{ inputs.expected_sha }}" in text


def test_backend_release_scans_generates_sbom_signs_and_attests() -> None:
    text, _ = _workflow()

    assert "anchore/scan-action@1638637db639e0ade3258b51db49a9a137574c3e" in text
    assert "severity-cutoff: high" in text
    assert "Inventory all candidate vulnerabilities" in text
    assert "Block fixable high and critical vulnerabilities" in text
    assert "only-fixed: true" in text
    assert "anchore/sbom-action@e22c389904149dbc22b58101806040fa8d37a610" in text
    assert "cosign sign --yes" in text
    assert "actions/attest-build-provenance@e8998f949152b193b063cb0ec769d69d929409be" in text
    assert "subject-digest: ${{ steps.publish.outputs.digest }}" in text


def test_backend_release_uses_pinned_actions_and_external_secrets() -> None:
    text, workflow = _workflow()

    action_lines = [line.strip() for line in text.splitlines() if "uses:" in line]
    assert action_lines
    assert all("@" in line and len(line.rsplit("@", 1)[1]) == 40 for line in action_lines)
    login = next(
        step
        for step in workflow["jobs"]["release"]["steps"]
        if step.get("name") == "Log in to Quay"
    )
    assert login["with"]["username"] == "${{ secrets.LAUNCHPAD_QUAY_USERNAME }}"
    credential_fields = set(login["with"]) - {"registry", "username"}
    assert len(credential_fields) == 1
    credential_value = login["with"][credential_fields.pop()]
    assert credential_value == "${{ secrets.LAUNCHPAD_QUAY_TOKEN }}"
