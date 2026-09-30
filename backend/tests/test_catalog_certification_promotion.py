import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "promote_catalog_certification", ROOT / "scripts/promote_catalog_certification.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path, *, blocker: str | None = None):
    catalog_id = "example-lab"
    (tmp_path / "catalog" / catalog_id).mkdir(parents=True)
    (tmp_path / "catalog-onboarding").mkdir()
    (tmp_path / "certification/catalog").mkdir(parents=True)
    catalog = {
        "catalog_item_id": catalog_id,
        "status": "draft",
        "metadata": {"certification_stage": "pending", "max_workshop_seats": 5},
    }
    certification = {
        "stage": "pending",
        "certified_seats": 0,
        "max_workshop_seats": 5,
        "promotion_sequence": [1, 5],
        "activation_blockers": [
            "one-seat Flightpath proof is not yet GREEN-live",
            "five-seat Flightpath proof is not yet GREEN-live",
            *([blocker] if blocker else []),
        ],
    }
    intake = {
        "catalog": {"catalog_item_id": catalog_id, "version": "1.0.0", "status": "draft"},
        "certification": certification,
    }
    contract = {"metadata": {"catalog_item_id": catalog_id}}
    catalog_path = tmp_path / "catalog" / catalog_id / "catalog-item.yaml"
    intake_path = tmp_path / "catalog-onboarding" / f"{catalog_id}.yaml"
    contract_path = tmp_path / "certification/catalog" / f"{catalog_id}.yaml"
    catalog_path.write_text(yaml.safe_dump(catalog))
    intake_path.write_text(yaml.safe_dump(intake))
    contract_path.write_text(yaml.safe_dump(contract))
    return catalog_id, contract_path


def _evidence(tmp_path: Path, catalog_id: str, contract_path: Path, seats: int):
    path = tmp_path / f"{catalog_id}-{seats}.json"
    payload = {
        "schema": "launchpad.redhat.com/catalog-certification-evidence/v1",
        "catalog_item_id": catalog_id,
        "result": "GREEN-live",
        "contract": {
            "catalog_version": "1.0.0",
            "path": f"certification/catalog/{catalog_id}.yaml",
            "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        },
        "plan": {"cluster_ref": "flightpath", "seats": seats},
        "rubric": {"passed": True, "score": 100},
        "promotion": {"eligible": True},
        "cleanup": {"status": "completed", "resource_counts": {"namespaces": 0}},
    }
    path.write_text(json.dumps(payload))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    return path


def test_promotion_requires_the_next_declared_scale_and_exact_checksum(tmp_path):
    catalog_id, contract_path = _fixture(tmp_path)
    evidence = _evidence(tmp_path, catalog_id, contract_path, 5)

    with pytest.raises(ValueError, match="next_scale"):
        MODULE.validate_promotion(root=tmp_path, catalog_id=catalog_id, evidence_path=evidence)

    evidence.write_text(evidence.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum"):
        MODULE.validate_promotion(root=tmp_path, catalog_id=catalog_id, evidence_path=evidence)


def test_one_then_five_seat_evidence_activates_only_after_all_blockers_clear(tmp_path):
    catalog_id, contract_path = _fixture(tmp_path)
    one = _evidence(tmp_path, catalog_id, contract_path, 1)
    result = MODULE.promote(root=tmp_path, catalog_id=catalog_id, evidence_path=one)
    assert result["status"] == "draft"
    assert result["certified_seats"] == 1

    five = _evidence(tmp_path, catalog_id, contract_path, 5)
    result = MODULE.promote(root=tmp_path, catalog_id=catalog_id, evidence_path=five)
    assert result["status"] == "active"
    assert result["certified_seats"] == 5
    promoted_catalog = yaml.safe_load(
        (tmp_path / "catalog" / catalog_id / "catalog-item.yaml").read_text()
    )
    assert promoted_catalog["metadata"]["activation_blockers"] == []


def test_non_proof_blocker_keeps_five_seat_catalog_draft(tmp_path):
    catalog_id, contract_path = _fixture(tmp_path, blocker="make image public")
    MODULE.promote(
        root=tmp_path,
        catalog_id=catalog_id,
        evidence_path=_evidence(tmp_path, catalog_id, contract_path, 1),
    )
    result = MODULE.promote(
        root=tmp_path,
        catalog_id=catalog_id,
        evidence_path=_evidence(tmp_path, catalog_id, contract_path, 5),
    )
    assert result["status"] == "draft"
    assert result["remaining_blockers"] == ["make image public"]
