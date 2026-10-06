from pathlib import Path

import yaml
from app.services.catalog_certification import (
    load_certification_contract,
    validate_certification_contract,
)
from app.services.catalog_onboarding import load_intake

ROOT = Path(__file__).resolve().parents[2]


def _assert_exact_flightpath_contract(
    catalog_id: str,
    version: str,
    probe: str,
    max_workshop_seats: int = 1,
    scale_profiles: tuple[int, ...] = (1, 5),
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
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == list(
        scale_profiles
    )


def test_hybrid_fraud_exact_release_has_a_flightpath_certification_contract():
    _assert_exact_flightpath_contract(
        "hybrid-fraud-detection",
        "0.1.2-flightpath.3",
        "scripts/certify-hybrid-fraud-seat.sh",
        1,
        (1,),
    )
    intake = load_intake(ROOT / "catalog-onboarding/hybrid-fraud-detection.yaml")
    assert intake["runtime"]["workload"]["helm_values"]["app"]["image"].endswith(
        "@sha256:faa4b11c6e314bf3f995b13153c7fa061bcba862753fe3f97b2488d4c117eb03"
    )
    assert intake["catalog"]["status"] == "active"
    assert intake["sources"]["workload"]["revision"] == (
        "2ea5e1f5cfce7e7a45e9b10408d8653590a4af79"
    )
    assert intake["certification"]["stage"] == "1-seat-certified"
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
        (1,),
    )
    intake = load_intake(ROOT / "catalog-onboarding/agent-reliability.yaml")
    assert intake["catalog"]["status"] == "active"
    assert intake["sources"]["showroom"]["revision"] == (
        "fa6a1797662e10eced38cc3cfd5fee4f52ecc7fc"
    )
    assert intake["certification"]["stage"] == "1-seat-certified"
    image = intake["runtime"]["workload"]["helm_values"]["image"]
    assert image["repository"] == "ghcr.io/jkershawrh/agent-reliability-quickstart"
    assert image["digest"] == (
        "sha256:eca79307a3a23e9314bd050a8f944f00a88f2869f55b24c925551b545984dc00"
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


def test_network_operations_exact_release_is_one_seat_certified_for_internal_and_public():
    exact_revision = "225af4a33489ffc4e8ac26fbbd6bc2b975512aab"
    contract_path = ROOT / "certification/catalog/network-operations-agent.yaml"
    contract = load_certification_contract(contract_path)
    intake = load_intake(ROOT / "catalog-onboarding/network-operations-agent.yaml")
    catalog = yaml.safe_load(
        (ROOT / "catalog/network-operations-agent/catalog-item.yaml").read_text()
    )
    review = yaml.safe_load(
        (ROOT / "evidence/lab-experience-review-20260930.yaml").read_text()
    )["labs"]["network-operations-agent"]
    overlay = (ROOT / "deploy/launchpad/overlays/flightpath-candidate/network-operations-agent.catalog-item.yaml").read_text()

    assert validate_certification_contract(
        contract,
        intake=intake,
        repo_root=ROOT,
        contract_path=contract_path,
    ) == []
    assert intake["catalog"]["version"] == "0.2.1-flightpath.11"
    assert contract["spec"]["target_cluster"] == "flightpath"
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [1]
    assert contract["spec"]["seat_probe"]["argv"][1] == "scripts/certify-network-operations-seat.sh"
    assert intake["sources"]["showroom"]["revision"] == exact_revision
    assert intake["sources"]["workload"]["revision"] == exact_revision
    assert catalog["metadata"]["showroom_content_ref"] == exact_revision
    assert catalog["metadata"]["source_content_revision"] == exact_revision
    assert catalog["metadata"]["workload_revision"] == exact_revision
    assert review["source_state"]["published_head"] == exact_revision
    assert review["source_state"]["catalog_pinned_revision"] == exact_revision
    assert review["source_state"]["image_provenance"]["image_source_revision"] == (
        exact_revision
    )
    assert intake["runtime"]["workload"]["helm_values"]["image"]["digest"] == (
        "sha256:9390dc029162a51995d407de99f5e1050901ab2b3ab9ecffaeb7d3bb550c9e9e"
    )
    assert intake["catalog"]["status"] == "active"
    assert intake["certification"]["stage"] == "1-seat-certified"
    assert intake["certification"]["certified_seats"] == 1
    assert intake["certification"]["promotion_sequence"] == [1]
    assert intake["certification"]["activation_blockers"] == []
    assert intake["runtime"]["allowed_exposure_policies"] == [
        "internal",
        "public_code",
    ]
    assert intake["certification"]["max_workshop_seats"] == 1
    assert "status: active" in overlay
    assert "certification_stage: 1-seat-certified" in overlay
    assert "public_access_certification_stage: one-seat-certified" in overlay
    assert "public_max_workshop_seats: 1" in overlay
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
        scale_profiles = [p["seats"] for p in contract["spec"]["scale_profiles"]]
        assert scale_profiles[0] == 1
        assert set(scale_profiles) <= {1, 5}
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
        assert intake["certification"]["certified_seats"] >= 1
        assert intake["certification"]["activation_blockers"] == []
        assert catalog["status"] == "active"
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
