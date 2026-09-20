from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
CONTRACT = ROOT / "contracts/capacity-admission-v1.yaml"


def test_capacity_admission_contract_is_versioned_and_whole_workshop_only():
    contract = yaml.safe_load(CONTRACT.read_text())
    schemas = contract["components"]["schemas"]

    assert contract["info"]["version"] == "1.0.0"
    request = schemas["WorkshopCapacityRequest"]
    assert request["properties"]["placement_policy"]["const"] == ("single_cluster_per_workshop")
    assert {
        "idempotency_key",
        "forecast_ref",
        "event_id",
        "workshop_id",
        "catalog_id",
        "catalog_release",
        "cluster_ref",
        "seats",
        "infrastructure_per_seat",
        "inference_per_seat",
    } <= set(request["required"])
    decision = schemas["CapacityAdmissionDecision"]
    assert set(decision["properties"]["status"]["enum"]) == {
        "accepted",
        "rejected",
    }
    assert "reserved_seats" in decision["required"]
    assert "limiting_dimensions" in decision["required"]


def test_reconciliation_contract_carries_forecast_and_operational_dimensions():
    schemas = yaml.safe_load(CONTRACT.read_text())["components"]["schemas"]
    record = schemas["CapacityAdmissionRecord"]

    assert {
        "forecast_ref",
        "event_id",
        "workshop_id",
        "catalog_id",
        "catalog_release",
        "cluster_ref",
        "model_id",
        "model_release",
        "decision_status",
        "reservation_status",
    } <= set(record["required"])
    reconciliation = schemas["CapacityReconciliationSnapshot"]
    assert {
        "status",
        "active_reservations",
        "active_seats",
        "active_infrastructure",
        "active_inference",
        "exceeded_dimensions",
        "records",
    } <= set(reconciliation["required"])


def test_reservation_contract_requires_cleanup_evidence_before_release():
    schemas = yaml.safe_load(CONTRACT.read_text())["components"]["schemas"]
    reservation = schemas["AggregateCapacityReservation"]

    assert {
        "reservation_id",
        "decision_id",
        "forecast_ref",
        "event_id",
        "workshop_id",
        "catalog_id",
        "catalog_release",
        "cluster_ref",
        "model_id",
        "model_release",
        "resources",
        "status",
        "created_at",
        "released_at",
        "cleanup_evidence_id",
    } <= set(reservation["required"])
    assert set(reservation["properties"]["status"]["enum"]) == {
        "held",
        "released",
    }
    assert reservation["properties"]["cleanup_evidence_id"]["pattern"] == (
        "^sha256:[0-9a-f]{64}$"
    )
