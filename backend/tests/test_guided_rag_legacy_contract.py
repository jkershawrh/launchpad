from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/guided-rag-on-xeon/catalog-item.yaml"


def test_guided_rag_is_an_explicit_non_orderable_legacy_reference():
    item = yaml.safe_load(CATALOG.read_text())
    metadata = item["metadata"]

    assert item["status"] == "deprecated"
    assert metadata["certification_stage"] == "deprecated-legacy"
    assert metadata["replacement_catalog_item_id"] == "intel-llm-cpu-serving"
    assert metadata["certification_transfer"] == "none"
    assert any("Do not order or certify" in blocker for blocker in metadata["activation_blockers"])


def test_guided_rag_does_not_masquerade_as_an_immutable_certified_lab():
    item = yaml.safe_load(CATALOG.read_text())
    metadata = item["metadata"]

    assert metadata["showroom_content_ref"] == "main"
    assert any("mutable" in blocker.lower() for blocker in metadata["activation_blockers"])
    assert not (ROOT / "catalog-onboarding/guided-rag-on-xeon.yaml").exists()
    assert not (ROOT / "certification/catalog/guided-rag-on-xeon.yaml").exists()
