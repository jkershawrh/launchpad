from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/keycloak-release.yml"


def _source() -> str:
    return WORKFLOW.read_text()


def test_keycloak_release_is_manual_exact_revision_and_immutable():
    source = _source()
    workflow = yaml.safe_load(source)

    assert "workflow_dispatch" in workflow[True]
    assert "expected_sha" in workflow[True]["workflow_dispatch"]["inputs"]
    assert 'test "${{ github.sha }}" = "${{ inputs.expected_sha }}"' in source
    assert "ghcr.io/${{ github.repository_owner }}/launchpad-keycloak" in source
    assert "digest_ref" in source
    assert "sha256:[0-9a-f]{64}" in source


def test_keycloak_release_runs_contracts_and_supply_chain_gates():
    source = _source()

    assert "test_keycloak_authenticator_contract.py" in source
    assert "test_public_gateway_availability_contract.py" in source
    assert "actions/setup-java@" in source
    assert 'java-version: "17"' in source
    assert "mvn -B -f keycloak-authenticator/pom.xml package" in source
    assert "only-fixed: true" in source
    assert "sbom.spdx.json" in source
    assert "cosign sign --yes" in source
    assert "actions/attest-build-provenance" in source
    assert 'schema_version:"launchpad.redhat.com/keycloak-release/v1"' in source


def test_keycloak_release_builds_only_the_authenticator_context_for_amd64():
    source = _source()

    assert "context: keycloak-authenticator" in source
    assert "file: keycloak-authenticator/Containerfile" in source
    assert "platforms: linux/amd64" in source
    assert "backend/Containerfile" not in source
    assert "frontend/Containerfile" not in source


def test_flightpath_promotion_verifies_digest_attestation_and_signature():
    source = (ROOT / "scripts/promote-flightpath-keycloak.sh").read_text()

    assert "api.flightpath.fm2aihpcsed.com:6443" in source
    assert "ghcr\\.io/rhpds/launchpad-keycloak@sha256:" in source
    assert 'gh attestation verify "oci://$image" --repo rhpds/launchpad' in source
    assert 'cosign verify "$image"' in source
    assert "token.actions.githubusercontent.com" in source
    assert "patch keycloak keycloak" in source
    assert "What you can do in Launchpad" in source
