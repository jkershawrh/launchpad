from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_sandbox_image_has_no_baked_or_fallback_password():
    containerfile = (ROOT / "demos/containers/sandbox/Containerfile").read_text()
    entrypoint = (ROOT / "demos/containers/sandbox/entrypoint.sh").read_text()

    assert "lab-user:launchpad" not in containerfile
    assert "passwd -l lab-user" in containerfile
    assert "SSH_PASSWORD:-launchpad" not in entrypoint
    assert "SSH_PASSWORD is required" in entrypoint


def test_sandbox_base_and_release_path_are_immutable_and_public_registry_ready():
    containerfile = (ROOT / "demos/containers/sandbox/Containerfile").read_text()
    workflow = (ROOT / ".github/workflows/sandbox-release.yml").read_text()

    assert "registry.access.redhat.com/ubi9/python-311@sha256:" in containerfile
    assert "dnf upgrade -y --refresh" in containerfile
    assert "ARG CODE_SERVER_VERSION=4.139.1" in containerfile
    assert "expected_sha:" in workflow
    assert "ref: ${{ inputs.expected_sha }}" in workflow
    assert 'test "$(git rev-parse HEAD)" = "${{ inputs.expected_sha }}"' in workflow
    assert "platforms: linux/amd64" in workflow
    assert "Full vulnerability inventory" in workflow
    assert "Block fixable high and critical vulnerabilities" in workflow
    assert "Generate the SBOM" in workflow
    assert "Sign the published digest with GitHub OIDC" in workflow
    assert "attest-build-provenance" in workflow
    assert "image-digest.txt" in workflow


def test_flightpath_uses_the_exact_published_sandbox_digest():
    patch = yaml.safe_load(
        (ROOT / "deploy/launchpad/overlays/flightpath-candidate/patch-configmap.yaml").read_text()
    )
    intake = yaml.safe_load((ROOT / "catalog-onboarding/ai-sandbox.yaml").read_text())
    image = patch["data"]["SANDBOX_IMAGE"]

    assert image == (
        "ghcr.io/jkershawrh/launchpad-sandbox@"
        "sha256:5fe2a362fe8e751b5e1fd200e7ba48118cf9e1d2141cdcfcee15075af5cc825c"
    )
    assert intake["runtime"]["image"]["digest"] in image
