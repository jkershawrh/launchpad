import json
import sqlite3
from pathlib import Path

import pytest
from app.services.vef_receipt_ledger import VEFReceiptLedger

KEY = b"local-test-ledger-key-not-for-production"


def _receipts() -> list[dict]:
    base = {"schema_version": "launchpad.vef-aggregate-receipt.v1", "pilot_id": "pilot-1"}
    records = {
        "a": (
            "track_outcome",
            {
                "track_id": "serve-llms",
                "provisioned_seats": 30,
                "activated_journeys": 28,
                "successful_journeys": 25,
                "failed_journeys": 2,
                "unknown_outcomes": 1,
                "evidence_state": "authoritative",
            },
        ),
        "b": (
            "platform_lifecycle",
            {
                "measurement_state": "authoritative",
                "orders_requested": 1,
                "seats_requested": 30,
                "seats_ready": 30,
                "seats_reclaimed": 30,
                "provisioning_p95_seconds": 92.5,
                "reclaim_p95_seconds": 61.0,
                "human_interventions": 1,
                "residue_count": 0,
            },
        ),
        "c": (
            "ai_usage",
            {
                "measurement_state": "authoritative",
                "actual_requests": 400,
                "input_tokens": 12000,
                "output_tokens": 6000,
                "inference_cost_usd": 18.25,
            },
        ),
        "d": (
            "cost_allocation",
            {
                "measurement_state": "authoritative",
                "allocation_basis": "successful_journey",
                "shared_platform_cost_usd": 100.0,
                "delivery_cost_usd": 200.0,
                "allocated_inference_cost_usd": 18.25,
                "unallocated_cost_usd": 0.0,
                "cost_center_ready": True,
                "chargeback_ready": True,
            },
        ),
    }
    return [
        {**base, "receipt_id": "sha256:" + marker * 64, "kind": kind, "data": data}
        for marker, (kind, data) in records.items()
    ]


def test_complete_batch_is_durable_and_exact_replay_is_idempotent(tmp_path: Path) -> None:
    ledger = VEFReceiptLedger(tmp_path / "vef.db", integrity_key=KEY)
    first = ledger.append_batch(_receipts())
    replay = ledger.append_batch(_receipts())
    assert first == {"inserted": 4, "replayed": 0, "pilot_id": "pilot-1"}
    assert replay == {"inserted": 0, "replayed": 4, "pilot_id": "pilot-1"}
    assert ledger.load_pilot("pilot-1") == _receipts()


def test_conflicting_replay_rolls_back_whole_batch(tmp_path: Path) -> None:
    ledger = VEFReceiptLedger(tmp_path / "vef.db", integrity_key=KEY)
    ledger.append_batch(_receipts())
    changed = _receipts()
    changed[0]["data"]["successful_journeys"] = 24
    changed[0]["data"]["failed_journeys"] = 3
    with pytest.raises(ValueError, match="conflicting receipt replay"):
        ledger.append_batch(changed)
    assert ledger.load_pilot("pilot-1") == _receipts()


def test_incomplete_or_sensitive_batch_is_never_persisted(tmp_path: Path) -> None:
    path = tmp_path / "vef.db"
    ledger = VEFReceiptLedger(path, integrity_key=KEY)
    with pytest.raises(ValueError):
        ledger.append_batch(_receipts()[:-1])
    sensitive = _receipts()
    sensitive[0]["data"]["email"] = "private@example.test"
    with pytest.raises(ValueError, match="sensitive field"):
        ledger.append_batch(sensitive)
    assert ledger.load_pilot("pilot-1") == []


def test_database_tampering_is_detected_before_replay(tmp_path: Path) -> None:
    path = tmp_path / "vef.db"
    ledger = VEFReceiptLedger(path, integrity_key=KEY)
    ledger.append_batch(_receipts())
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT receipt_id, payload_json FROM vef_receipts LIMIT 1"
        ).fetchone()
        payload = json.loads(row[1])
        payload["data"]["track_id"] = "tampered"
        connection.execute(
            "UPDATE vef_receipts SET payload_json = ? WHERE receipt_id = ?",
            (json.dumps(payload), row[0]),
        )
    with pytest.raises(ValueError, match="ledger integrity verification failed"):
        ledger.load_pilot("pilot-1")


def test_weak_or_missing_integrity_key_is_rejected(tmp_path: Path) -> None:
    for key in (b"", b"short"):
        with pytest.raises(ValueError, match="integrity key"):
            VEFReceiptLedger(tmp_path / "vef.db", integrity_key=key)
