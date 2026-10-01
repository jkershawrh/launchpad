from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/virtualization-ai-foundations-101/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/virtualization-ai-foundations-101.yaml"
CERTIFICATION = ROOT / "certification/catalog/virtualization-ai-foundations-101.yaml"
CERTIFIER = ROOT / "scripts/certify-virtualization-ai-seat.sh"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_101_records_certification_without_claiming_browser_console_sso() -> None:
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    contract = _load(CERTIFICATION)
    metadata = catalog["metadata"]

    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert intake["certification"]["certified_seats"] == 1
    assert metadata["certification_stage"] == "1-seat-certified"
    assert metadata["workload_revision"] == "e74393d0def1a7a2749911b3a421c62f3f1c2558"
    assert metadata["recommended_next_items"] == ["virtualization-ai-201"]
    assert intake["learning"]["recommended_next_items"] == ["virtualization-ai-201"]
    assert metadata["showroom_tabs"] == intake["runtime"]["tabs"]
    assert metadata["showroom_tabs"][0] == {
        "id": "story",
        "title": "Story",
        "source": "workload.route.ui",
        "path": "/",
    }
    assert [tab["id"] for tab in metadata["showroom_tabs"]] == [
        "story",
        "terminal",
        "openshift-console",
    ]
    assert metadata["required_models"] == intake["runtime"]["required_models"] == [
        "granite-3.2-8b-tools"
    ]
    assert metadata["workload_helm_values"]["adapter"]["mode"] == "live"
    assert metadata["workload_helm_values"]["adapter"]["model"]["name"] == (
        "granite-3.2-8b-tools"
    )

    assert metadata["showroom_content_repo_url"].startswith(
        "https://github.com/"
    )
    assert metadata["workload_repo"].startswith("https://github.com/")
    for source in intake["sources"].values():
        assert source["gitops_repo_url"].startswith("https://github.com/")

    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    assert {"path": "journey.source_state", "equals": "LIVE"} in assertions
    assert {
        "path": "journey.request_origin",
        "equals": "operations-vm",
    } in assertions
    assert {"path": "journey.outcome", "equals": "live-advisory"} in assertions
    assert {"path": "journey.model_participated", "equals": True} in assertions
    assert {
        "path": "journey.model",
        "equals": "granite-3.2-8b-tools",
    } in assertions
    assert {"path": "journey.hardware", "equals": "Intel Xeon CPU"} in assertions
    assert {"path": "journey.human_authority_preserved", "equals": True} in assertions
    assert metadata["activation_blockers"] == []
    assert metadata["activation_blockers"] == intake["certification"][
        "activation_blockers"
    ]
    assert metadata["certification_transfer"] == "none"
    assert {"path": "operator_journey.console_url_present", "equals": True} in assertions


def test_101_certifier_waits_for_the_vm_guest_path() -> None:
    script = CERTIFIER.read_text(encoding="utf-8")

    assert "for _ in {1..40}; do" in script
    assert 'sleep 3' in script
    assert 'printf \'%s\\n\' "$response"' in script
    assert '--command="sudo env LAB_NAMESPACE=$namespace' in script
    assert 'lab@vm/operations-vm' in script
    assert "--local-ssh-opts='-o StrictHostKeyChecking=no'" in script
    assert "--local-ssh-opts='-o UserKnownHostsFile=/dev/null'" in script
    assert "key_path=/tmp/launchpad-certification/lab-key" in script
