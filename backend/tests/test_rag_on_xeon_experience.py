import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/rag-on-xeon/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/rag-on-xeon.yaml"
CERTIFICATION = ROOT / "certification/catalog/rag-on-xeon.yaml"
EVIDENCE = (
    ROOT
    / "evidence/runs/staging-candidate-e2d78de/"
    "flightpath-e2d78de-20260929T124528Z-7fpm8-rag-on-xeon-five-seat.json"
)
SEAT_PROBE = ROOT / "scripts/certify-cpu-serving-catalog-seat.sh"
RAG_PROBE = ROOT / "scripts/certify-cpu-serving-rag.sh"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_current_rag_entry_is_exactly_the_certified_compatibility_alias() -> None:
    catalog = _yaml(CATALOG)
    intake = _yaml(INTAKE)
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    metadata = catalog["metadata"]

    assert catalog["catalog_item_id"] == intake["catalog"]["catalog_item_id"] == (
        "rag-on-xeon"
    )
    assert metadata["migration_mode"] == "compatibility_alias"
    assert metadata["canonical_item_id"] == intake["runtime"][
        "compatibility_alias_of"
    ] == "intel-llm-cpu-serving"
    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert metadata["certification_stage"] == intake["certification"]["stage"] == (
        "5-seat-certified"
    )
    assert intake["certification"]["certified_seats"] == 5
    assert metadata["showroom_content_ref"] == intake["sources"]["showroom"][
        "revision"
    ] == "9526ede61b5c31949f3a1bedd133b5a17e554178"
    assert intake["sources"]["workload"]["revision"] == (
        "88867e14b1eede7d9aa563069aa093c122a4a53a"
    )

    expected_hash = EVIDENCE.with_suffix(".json.sha256").read_text().split()[0]
    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected_hash
    assert evidence["contract"]["sha256"] == hashlib.sha256(
        CERTIFICATION.read_bytes()
    ).hexdigest()
    assert evidence["result"] == "GREEN-live"
    assert evidence["rubric"]["score"] == 100
    assert len(evidence["seat_results"]) == 5
    for seat in evidence["seat_results"]:
        result = seat["probe"]["result"]
        assert result["rag_journey"]["grounded_answer"] is True
        assert "model_journey" not in result
        assert "cross_namespace=DENIED" in result["terminal_scope"]
        assert "node_list=DENIED" in result["terminal_scope"]
    assert evidence["cleanup"]["model_keys_revoked"] is True
    assert all(count == 0 for count in evidence["cleanup"]["resource_counts"].values())


def test_next_rag_certificate_requires_retrieval_and_exact_managed_model_identity() -> None:
    seat_probe = SEAT_PROBE.read_text(encoding="utf-8")
    rag_probe = RAG_PROBE.read_text(encoding="utf-8")

    assert 'title == "orion-leave-policy.txt"' in rag_probe
    assert 'contains("17")' in rag_probe
    assert ".configured_model == .observed_model" in seat_probe
    assert "model_journey: $model_observation" in seat_probe
    assert "curl_options=(" in rag_probe
    assert "-fsS" in rag_probe
    assert "-fsSk" not in rag_probe  # Flightpath must use the trusted route chain.
