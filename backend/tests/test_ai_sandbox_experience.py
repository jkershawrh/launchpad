from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/ai-sandbox/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/ai-sandbox.yaml"
CERTIFICATION = ROOT / "certification/catalog/ai-sandbox.yaml"
GUIDE = ROOT / "demos/containers/sandbox/guided-start.md"
CONTAINERFILE = ROOT / "demos/containers/sandbox/Containerfile"
OC_COMPAT = ROOT / "demos/containers/sandbox/oc-compat"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_ai_sandbox_is_active_only_after_exact_image_live_certification() -> None:
    catalog = _yaml(CATALOG)
    intake = _yaml(INTAKE)
    contract = _yaml(CERTIFICATION)
    metadata = catalog["metadata"]

    assert catalog["catalog_item_id"] == intake["catalog"]["catalog_item_id"] == (
        "ai-sandbox"
    )
    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert metadata["certification_stage"] == intake["certification"]["stage"] == (
        "1-seat-certified"
    )
    assert intake["certification"]["certified_seats"] == 1
    assert metadata["activation_blockers"] == intake["certification"][
        "activation_blockers"
    ]
    assert metadata["activation_blockers"] == []
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [1, 5]


def test_ai_sandbox_surfaces_and_managed_model_contract_are_coherent() -> None:
    catalog = _yaml(CATALOG)
    intake = _yaml(INTAKE)
    metadata = catalog["metadata"]
    runtime = intake["runtime"]

    assert metadata["access_methods"] == runtime["access_methods"] == [
        "openshift_console",
        "web_terminal",
        "vscode",
    ]
    assert [tab["id"] for tab in runtime["tabs"]] == [
        "web-terminal",
        "browser-ide",
        "openshift-console",
    ]
    assert metadata["required_models"] == runtime["required_models"] == [
        "granite-2b-cpu"
    ]
    assert metadata["inference_endpoint"] == runtime["inference_endpoint"] == (
        "litellm_virtual_key_candidate"
    )
    assert runtime["deployment_type"] == "sandbox"
    assert runtime["image"]["digest"].startswith("sha256:")
    assert runtime["image"]["digest"] == (
        "sha256:0faa22c48b50e9f896788ef3d4380282c8fed75f4a4c8a437236a47a608ac452"
    )
    assert runtime["image"]["source_revision"] == (
        "c5de4b259cfb014f5e1c6d931e9e7b1a63ce54e2"
    )
    assert metadata["workload_revision"] == runtime["image"]["source_revision"]

    guide = GUIDE.read_text(encoding="utf-8")
    normalized_guide = " ".join(guide.split())
    for stage in ("## Show", "## Learn", "## Do", "## Prove", "## Clean up"):
        assert stage in guide
    assert "managed `granite-2b-cpu` model assigned to this seat" in normalized_guide
    assert "does not deploy or claim a local model server" in normalized_guide
    assert "never chooses a different advertised model" in normalized_guide
    assert "guided-start-proof.json" in guide


def test_ai_sandbox_uses_a_pinned_minimal_cluster_client_and_no_jupyter() -> None:
    containerfile = CONTAINERFILE.read_text(encoding="utf-8")
    oc_compat = OC_COMPAT.read_text(encoding="utf-8")

    assert "KUBECTL_VERSION=v1.37.1" in containerfile
    assert "KUBECTL_SHA256=65691ff77eb6fa44c908b77a1082c9f092c3b9733b5cefabec0d1104890e21a8" in containerfile
    assert "sha256sum -c -" in containerfile
    assert "mirror.openshift.com" not in containerfile
    assert "openshift-client-linux" not in containerfile
    assert "jupyterlab" not in containerfile
    assert "EXPOSE 2222 8443" in containerfile
    assert '"project"' in oc_compat
    assert '"whoami"' in oc_compat
    assert 'exec kubectl "$@"' in oc_compat


def test_ai_sandbox_patches_code_server_runtime_dependency() -> None:
    containerfile = CONTAINERFILE.read_text(encoding="utf-8")

    assert "CODE_SERVER_VERSION=4.139.1" in containerfile
    assert "undici-7.29.1.tgz" in containerfile
    assert '\"version\": \"7.29.1\"' in containerfile
    assert "dnf remove -y npm nodejs" in containerfile


def test_ai_sandbox_certification_runs_the_full_guided_journey() -> None:
    contract = _yaml(CERTIFICATION)
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    expected = {(row["path"], row.get("equals")) for row in assertions}
    script = (ROOT / "scripts/certify-ai-sandbox-seat.sh").read_text(encoding="utf-8")

    for assertion in (
        ("guided_journey.workload_status", "ready"),
        ("guided_journey.cleanup_status", "complete"),
        ("model.status", "live"),
        ("model.assigned_model", "granite-2b-cpu"),
        ("model.observed_model", "granite-2b-cpu"),
        ("model.inference_source", "launchpad-managed-endpoint"),
        ("model.participated", True),
    ):
        assert assertion in expected
    assert "launchpad-guided-start all" in script
    assert "guided-start-proof.json" in script
    assert '*/v1) ;;' in script
    assert '"${model_api_base}/models"' in script
