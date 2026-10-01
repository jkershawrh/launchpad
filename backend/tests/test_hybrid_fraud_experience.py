from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "catalog/hybrid-fraud-detection/catalog-item.yaml"
INTAKE_PATH = ROOT / "catalog-onboarding/hybrid-fraud-detection.yaml"
CERTIFICATION_PATH = ROOT / "certification/catalog/hybrid-fraud-detection.yaml"
OVERLAY_PATH = ROOT / (
    "deploy/launchpad/overlays/flightpath-candidate/"
    "hybrid-fraud-detection.catalog-item.yaml"
)
VULNERABILITY_EVIDENCE_PATH = ROOT / (
    "evidence/runs/catalog-intake-hybrid-fraud/"
    "exact-candidate-vulnerability-inventory-20261001.json"
)

SOURCE_REVISION = "2ea5e1f5cfce7e7a45e9b10408d8653590a4af79"
WORKLOAD_IMAGE = (
    "ghcr.io/jkershawrh/hybrid-fraud-detection@sha256:"
    "faa4b11c6e314bf3f995b13153c7fa061bcba862753fe3f97b2488d4c117eb03"
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_hybrid_fraud_exact_candidate_is_one_seat_certified_and_active() -> None:
    catalog = _load(CATALOG_PATH)
    intake = _load(INTAKE_PATH)
    metadata = catalog["metadata"]

    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert metadata["certification_stage"] == "1-seat-certified"
    assert intake["certification"]["stage"] == "1-seat-certified"
    assert metadata["max_workshop_seats"] == 1
    assert intake["certification"]["max_workshop_seats"] == 1
    assert metadata["certification_transfer"] == "none"
    assert intake["learning"]["certification_transfer"] == "none"
    assert metadata["activation_blockers"] == []
    assert metadata["activation_blockers"] == intake["certification"][
        "activation_blockers"
    ]
    assert intake["certification"]["certified_seats"] == 1


def test_hybrid_fraud_exact_candidate_vulnerability_disposition_is_recorded() -> None:
    evidence = _load(VULNERABILITY_EVIDENCE_PATH)

    assert evidence["subject"]["source_revision"] == SOURCE_REVISION
    assert evidence["subject"]["image"] == WORKLOAD_IMAGE
    assert evidence["scanner"]["name"] == "grype"
    assert evidence["scanner"]["version"] == "0.110.0"
    assert evidence["summary"]["critical_matches"] == 0
    assert evidence["critical_findings"] == []
    assert evidence["disposition"]["status"] == "security-gate-passed"
    assert evidence["disposition"]["activation_allowed"] is True


def test_hybrid_fraud_source_and_runtime_are_exactly_pinned() -> None:
    catalog = _load(CATALOG_PATH)
    intake = _load(INTAKE_PATH)
    metadata = catalog["metadata"]

    for key in (
        "showroom_content_ref",
        "workload_revision",
        "source_content_revision",
    ):
        assert metadata[key] == SOURCE_REVISION
    assert intake["sources"]["showroom"]["revision"] == SOURCE_REVISION
    assert intake["sources"]["workload"]["revision"] == SOURCE_REVISION
    assert metadata["workload_helm_values"]["app"]["image"] == WORKLOAD_IMAGE
    assert (
        intake["runtime"]["workload"]["helm_values"]["app"]["image"]
        == WORKLOAD_IMAGE
    )


def test_hybrid_fraud_operator_contract_matches_the_immutable_story() -> None:
    catalog = _load(CATALOG_PATH)
    intake = _load(INTAKE_PATH)
    overlay = _load(OVERLAY_PATH)
    metadata = catalog["metadata"]
    catalog_tabs = metadata["showroom_tabs"]
    intake_tabs = intake["runtime"]["tabs"]
    overlay_tabs = overlay["metadata"]["showroom_tabs"]

    assert [tab["id"] for tab in catalog_tabs] == [
        "terminal",
        "workspace",
        "openshift-console",
    ]
    assert [tab["id"] for tab in intake_tabs] == [
        "terminal",
        "workspace",
        "openshift-console",
    ]
    assert next(tab for tab in catalog_tabs if tab["id"] == "workspace")[
        "title"
    ] == "Hybrid Decision Casebook"
    assert next(tab for tab in intake_tabs if tab["id"] == "workspace")[
        "title"
    ] == "Hybrid Decision Casebook"
    assert next(tab for tab in overlay_tabs if tab["id"] == "workspace")[
        "title"
    ] == "Hybrid Decision Casebook"
    assert overlay["metadata"]["workspace_title"] == "Hybrid Decision Casebook"


def test_hybrid_fraud_certification_requires_real_participant_function() -> None:
    contract = _load(CERTIFICATION_PATH)
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    expected = {(item["path"], item.get("equals")) for item in assertions}

    assert ("result", "GREEN-live-internal-seat") in expected
    assert ("readiness.workspace_http_status", 200) in expected
    assert ("hybrid_journey.live_model", True) in expected
    assert ("hybrid_journey.model", "granite-3.2-8b-tools") in expected
    assert ("hybrid_journey.human_authority_preserved", True) in expected
    assert ("readiness.model_ready", True) in expected
    assert ("contains_sensitive_values", False) in expected
    assert contract["spec"]["cleanup"]["resources"]

    driver = (ROOT / "scripts/certify-hybrid-fraud-seat.sh").read_text(
        encoding="utf-8"
    )
    assert '.model == "granite-3.2-8b-tools"' in driver
    assert 'contains("not for real decisions")' in driver
