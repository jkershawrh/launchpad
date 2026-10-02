from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/virtualization-ai-201/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/virtualization-ai-201.yaml"
CERTIFICATION = ROOT / "certification/catalog/virtualization-ai-201.yaml"
SOURCE_REVISION = "3c94600ca8808a55693e94d5a1f169efbadbedd1"
PRESENTATION_IMAGE = (
    "ghcr.io/jkershawrh/virtualization-ai-201-presentation@sha256:"
    "2749e4ad44f3902f7507adaaaa8fadd509d1e625b33619530852bd9a01255069"
)
ADAPTER_IMAGE = (
    "ghcr.io/jkershawrh/virtualization-ai-201-adapter@sha256:"
    "99f1ac6f65386013cb20d81e3dbc6099ffbb63cebfdc6fb1f1cdd50d96153a39"
)
SHOWROOM_IMAGE = (
    "ghcr.io/jkershawrh/virtualization-ai-201-showroom-content@sha256:"
    "56991a08cba6849d42caa54ae45b4c7d2714b086d0df247f53cd2d4700b090ca"
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_201_requires_vm_origin_and_truthful_live_inference_before_certification() -> None:
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    contract = _load(CERTIFICATION)
    metadata = catalog["metadata"]
    runtime = intake["runtime"]

    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert intake["certification"]["certified_seats"] == 1
    assert intake["certification"]["stage"] == "1-seat-certified"
    assert metadata["allowed_exposure_policies"] == ["internal", "public_code"]
    assert runtime["allowed_exposure_policies"] == ["internal", "public_code"]
    assert metadata["recommended_next_items"] == ["virtualization-ai-301"]
    assert intake["learning"]["recommended_next_items"] == ["virtualization-ai-301"]
    assert metadata["showroom_tabs"] == runtime["tabs"]
    assert metadata["showroom_tabs"][0] == {
        "id": "story",
        "title": "Story",
        "source": "workload.route.ui",
        "path": "/",
    }
    assert metadata["showroom_content_repo_url"].startswith(
        "https://github.com/"
    )
    assert metadata["workload_repo"].startswith("https://github.com/")
    for source in intake["sources"].values():
        assert source["gitops_repo_url"].startswith("https://github.com/")
        assert source["revision"] == SOURCE_REVISION
    assert metadata["showroom_content_ref"] == SOURCE_REVISION
    assert metadata["showroom_content_playbook"] == "showroom/default-site.yml"
    assert intake["sources"]["showroom"]["playbook"] == "showroom/default-site.yml"
    assert metadata["workload_revision"] == SOURCE_REVISION
    assert metadata["showroom_content_image"] == SHOWROOM_IMAGE
    assert metadata["workload_helm_values"]["presentation_image"] == PRESENTATION_IMAGE
    assert metadata["workload_helm_values"]["workload_image"] == ADAPTER_IMAGE

    expected_private = {
        "source": "generated_ssh_keypair",
        "pair": "contract-author-vm",
        "part": "private",
    }
    assert metadata["workload_runtime_secret_sources"]["VM_SSH_PRIVATE_KEY"] == (
        expected_private
    )
    assert runtime["workload"]["runtime_secret_sources"]["VM_SSH_PRIVATE_KEY"] == (
        expected_private
    )
    assert metadata["workload_runtime_value_bindings"] == {
        "vm.sshAuthorizedKey": "VM_SSH_PUBLIC_KEY"
    }
    assert runtime["workload"]["runtime_value_bindings"] == {
        "vm.sshAuthorizedKey": "VM_SSH_PUBLIC_KEY"
    }

    assert metadata["required_models"] == runtime["required_models"] == [
        "granite-3.2-8b-tools"
    ]
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    assert {"path": "journey.source_state", "equals": "LIVE"} in assertions
    assert {
        "path": "journey.request_origin",
        "equals": "contract-author-vm",
    } in assertions
    assert {"path": "journey.human_authority_preserved", "equals": True} in assertions
    assert {"path": "journey.model_participated", "equals": True} in assertions
    assert {
        "path": "journey.model",
        "equals": "granite-3.2-8b-tools",
    } in assertions
    assert metadata["activation_blockers"] == []
    assert metadata["certification_transfer"] == "none"
    assert metadata["activation_blockers"] == intake["certification"][
        "activation_blockers"
    ]

    driver = (ROOT / "scripts/certify-virtualization-ai-seat.sh").read_text()
    assert "terminal_contract_author_request()" in driver
    assert "contract_author_response" in driver
    assert "oc get vmi contract-author-vm" in driver
    assert 'learner@"$vm_ip"' in driver
    assert "wait_for_resource vm" in driver
    assert "wait_for_resource vmi" in driver
    assert "scp -i" not in driver
    assert "/home/learner/vm_client.py" in driver
    assert "normalize_remote_json" in driver
    assert "/home/learner/vm_client.py" in driver
    assert "normalize_remote_json()" in driver
    assert "JSONDecoder" in driver
