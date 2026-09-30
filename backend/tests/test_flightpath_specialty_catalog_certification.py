from pathlib import Path

import yaml

from app.services.catalog_certification import (
    load_certification_contract,
    validate_certification_contract,
)
from app.services.catalog_onboarding import load_intake


ROOT = Path(__file__).resolve().parents[2]


def _assert_exact_flightpath_contract(
    catalog_id: str, version: str, probe: str, max_workshop_seats: int = 1
) -> None:
    contract_path = ROOT / f"certification/catalog/{catalog_id}.yaml"
    intake_path = ROOT / f"catalog-onboarding/{catalog_id}.yaml"
    contract = load_certification_contract(contract_path)
    intake = load_intake(intake_path)

    assert validate_certification_contract(
        contract,
        intake=intake,
        repo_root=ROOT,
        contract_path=contract_path,
    ) == []
    assert contract["spec"]["target_cluster"] == "flightpath"
    assert contract["spec"]["kubeconfig_server"] == (
        "https://api.flightpath.fm2aihpcsed.com:6443"
    )
    assert contract["spec"]["seat_probe"]["argv"][1] == probe
    assert intake["catalog"]["version"] == version
    assert intake["runtime"]["workshop_cluster_ref"] == "flightpath"
    assert intake["certification"]["max_workshop_seats"] == max_workshop_seats
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [1, 5]


def test_hybrid_fraud_exact_release_has_a_flightpath_certification_contract():
    _assert_exact_flightpath_contract(
        "hybrid-fraud-detection",
        "0.1.2-flightpath.2",
        "scripts/certify-hybrid-fraud-seat.sh",
        1,
    )
    intake = load_intake(ROOT / "catalog-onboarding/hybrid-fraud-detection.yaml")
    assert intake["runtime"]["workload"]["helm_values"]["app"]["image"].endswith(
        "@sha256:4a31d147c46bc3323a29777519347dc30555a325b29e1cef2b77c85984343f0e"
    )
    assert intake["catalog"]["status"] == "draft"
    assert intake["sources"]["workload"]["revision"] == (
        "9dccae859e939d836c06cc9fb51d8ae4a848a38f"
    )
    assert intake["certification"]["stage"] == "immutable-source-published"
    contract = load_certification_contract(
        ROOT / "certification/catalog/hybrid-fraud-detection.yaml"
    )
    assert all(
        page["path"].startswith("/www/hybrid-fraud-detection/main/")
        for page in contract["spec"]["showroom"]["pages"]
    )


def test_agent_reliability_exact_release_has_a_flightpath_certification_contract():
    _assert_exact_flightpath_contract(
        "agent-reliability",
        "0.1.1-flightpath.1",
        "scripts/certify-agent-reliability-seat.sh",
        1,
    )
    intake = load_intake(ROOT / "catalog-onboarding/agent-reliability.yaml")
    assert intake["catalog"]["status"] == "draft"
    assert intake["sources"]["showroom"]["revision"] == (
        "9c69348c34904c58997318d9124ac3d50661984b"
    )
    assert intake["certification"]["stage"] == "source-update-published"
    image = intake["runtime"]["workload"]["helm_values"]["image"]
    assert image["repository"] == "ghcr.io/jkershawrh/agent-reliability-quickstart"
    assert image["digest"] == (
        "sha256:604331d4a050f47457e27c2191106aa3fa075d408514143cd9eac6da18dfc3fb"
    )
    assert [tab["id"] for tab in intake["runtime"]["tabs"]] == [
        "terminal",
        "workspace",
        "openshift-console",
    ]
    contract = load_certification_contract(
        ROOT / "certification/catalog/agent-reliability.yaml"
    )
    assert all(
        page["path"].startswith("/www/agent-reliability-quickstart/main/")
        for page in contract["spec"]["showroom"]["pages"]
    )


def test_specialty_probes_cover_function_namespace_and_secret_boundaries():
    fraud = (ROOT / "scripts/certify-hybrid-fraud-seat.sh").read_text()
    reliability = (ROOT / "scripts/certify-agent-reliability-seat.sh").read_text()

    assert "/api/v1/score" in fraud
    assert '"llm_skipped"' not in fraud  # jq validates the field without echoing secrets.
    assert "cross_namespace=DENIED" in fraud
    assert "fraud-model-runtime" in fraud

    for expected in (
        "prompt_injection",
        "unauthorized_tool",
        "inference_timeout",
        "cross_namespace=DENIED",
        "model-connection",
    ):
        assert expected in reliability


def test_network_operations_exact_release_is_one_seat_certified_and_internal_only():
    contract_path = ROOT / "certification/catalog/network-operations-agent.yaml"
    contract = load_certification_contract(contract_path)
    intake = load_intake(ROOT / "catalog-onboarding/network-operations-agent.yaml")
    overlay = (ROOT / "deploy/launchpad/overlays/flightpath-candidate/network-operations-agent.catalog-item.yaml").read_text()

    assert validate_certification_contract(
        contract,
        intake=intake,
        repo_root=ROOT,
        contract_path=contract_path,
    ) == []
    assert intake["catalog"]["version"] == "0.2.1-flightpath.10"
    assert contract["spec"]["target_cluster"] == "flightpath"
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [1]
    assert contract["spec"]["seat_probe"]["argv"][1] == "scripts/certify-network-operations-seat.sh"
    assert intake["sources"]["workload"]["revision"] == (
        "6ed5c53337afa55c03949b2963b429f32977ef69"
    )
    assert intake["runtime"]["workload"]["helm_values"]["image"]["digest"] == (
        "sha256:a6ac58c4040127bdd790a2f2fd61c9eacf659f346d6c70d5da5dec06e7756242"
    )
    assert intake["catalog"]["status"] == "active"
    assert intake["certification"]["stage"] == "1-seat-certified"
    assert intake["certification"]["certified_seats"] == 1
    assert intake["certification"]["promotion_sequence"] == [1]
    assert intake["certification"]["activation_blockers"] == []
    assert intake["runtime"]["allowed_exposure_policies"] == ["internal"]
    assert intake["certification"]["max_workshop_seats"] == 1
    assert "status: active" in overlay
    assert "certification_stage: 1-seat-certified" in overlay
    assert "allowed_exposure_policies: [internal]" in overlay
    assert "max_workshop_seats: 1" in overlay

    probe = (ROOT / "scripts/certify-network-operations-seat.sh").read_text()
    for expected in (
        "/api/investigate",
        "/api/lab/qualify",
        "curl_options=(-fsSkL",
        "unverified_draft_for_human_review",
        "cross_namespace=DENIED",
        "network-operations-model-runtime",
    ):
        assert expected in probe


def test_every_legacy_migration_candidate_has_a_fail_closed_flightpath_proof_path():
    expected = {
        "ai-sandbox": "scripts/certify-ai-sandbox-seat.sh",
        "cpu-inference-serving": "scripts/certify-cpu-serving-catalog-seat.sh",
        "intel-llm-tool-calling": "scripts/certify-tool-calling-seat.sh",
        "openshift-operators-workshop": "scripts/certify-operator-workshop-seat.sh",
        "rag-on-xeon": "scripts/certify-cpu-serving-catalog-seat.sh",
    }

    for catalog_id, probe in expected.items():
        contract_path = ROOT / f"certification/catalog/{catalog_id}.yaml"
        intake_path = ROOT / f"catalog-onboarding/{catalog_id}.yaml"
        contract = load_certification_contract(contract_path)
        intake = load_intake(intake_path)
        catalog = yaml.safe_load(
            (ROOT / f"catalog/{catalog_id}/catalog-item.yaml").read_text()
        )

        assert validate_certification_contract(
            contract,
            intake=intake,
            repo_root=ROOT,
            contract_path=contract_path,
        ) == []
        assert contract["spec"]["target_cluster"] == "flightpath"
        assert [p["seats"] for p in contract["spec"]["scale_profiles"]] == [1, 5]
        assert contract["spec"]["seat_probe"]["argv"][1] == probe
        assert intake["runtime"]["workshop_cluster_ref"] == "flightpath"
        assert intake["certification"]["certified_seats"] in {0, 1, 5}
        expected_max = (
            1
            if catalog_id
            in {
                "ai-sandbox",
                "intel-llm-tool-calling",
                "openshift-operators-workshop",
            }
            else 5
        )
        assert intake["certification"]["max_workshop_seats"] == expected_max
        if intake["certification"]["certified_seats"] < 5:
            assert intake["certification"]["activation_blockers"]
        else:
            assert intake["certification"]["activation_blockers"] == []
        expected_status = "active" if intake["certification"]["certified_seats"] == 5 else "draft"
        assert catalog["status"] == expected_status
        assert "Arena" not in catalog
        assert "Oberon" not in catalog
        assert "github.com/rhpds/" not in catalog


def test_operator_workshop_probe_uses_namespaced_operator_reconciliation():
    probe = (ROOT / "scripts/certify-operator-workshop-seat.sh").read_text()

    assert "apiVersion: tekton.dev/v1" in probe
    assert "kind: PipelineRun" in probe
    assert "--for=condition=Succeeded" in probe
    assert "operator-reconciled:" in probe
    assert "hello-openshift" not in probe


def test_legacy_inference_entries_explicitly_reuse_the_proven_flightpath_runtime():
    for catalog_id in ("cpu-inference-serving", "rag-on-xeon"):
        intake = load_intake(ROOT / f"catalog-onboarding/{catalog_id}.yaml")
        catalog = (ROOT / f"catalog/{catalog_id}/catalog-item.yaml").read_text()

        assert intake["runtime"]["compatibility_alias_of"] == "intel-llm-cpu-serving"
        assert "migration_mode: compatibility_alias" in catalog
        assert "canonical_item_id: intel-llm-cpu-serving" in catalog
