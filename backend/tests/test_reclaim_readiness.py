"""Local-only pre-reclaim balance checks; no cluster access or mutation."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.services.reclaim_readiness import evaluate_reclaim_readiness, main

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
WORKSHOP = "11111111-1111-4111-8111-111111111111"
SESSION_1 = "22222222-2222-4222-8222-222222222222"
SESSION_2 = "33333333-3333-4333-8333-333333333333"
RESERVATION = "event-1:cohort-1:lab-1"


def _inventory():
    return {
        "schema_version": "reclaim-readiness/v1",
        "captured_at": (NOW - timedelta(minutes=2)).isoformat(),
        "scope": {
            "workshop_ids": [WORKSHOP],
            "cluster_refs": ["arena"],
            "workshops_complete": True,
            "sessions_complete": True,
            "namespaces_complete": True,
            "reservations_complete": True,
        },
        "workshops": [
            {
                "workshop_id": WORKSHOP,
                "cluster_ref": "arena",
                "seat_count": 2,
                "reservation_id": RESERVATION,
                "state": "ready",
            }
        ],
        "sessions": [
            {
                "session_id": SESSION_1,
                "workshop_id": WORKSHOP,
                "cluster_ref": "arena",
                "namespace": "launchpad-seat-1",
                "seat_number": 1,
                "state": "ready",
            },
            {
                "session_id": SESSION_2,
                "workshop_id": WORKSHOP,
                "cluster_ref": "arena",
                "namespace": "launchpad-seat-2",
                "seat_number": 2,
                "state": "ready",
            },
        ],
        "namespaces": [
            {
                "namespace": "launchpad-seat-1",
                "cluster_ref": "arena",
                "workshop_id": WORKSHOP,
                "session_id": SESSION_1,
            },
            {
                "namespace": "launchpad-seat-2",
                "cluster_ref": "arena",
                "workshop_id": WORKSHOP,
                "session_id": SESSION_2,
            },
        ],
        "reservations": [
            {
                "reservation_id": RESERVATION,
                "workshop_id": WORKSHOP,
                "cluster_ref": "arena",
                "seat_count": 2,
                "state": "consumed",
            }
        ],
    }


def _reason(payload):
    result = evaluate_reclaim_readiness(payload, now=NOW)
    assert not result.ready
    return result.reason


def test_balanced_inventory_is_ready_without_mutation():
    inventory = _inventory()
    before = deepcopy(inventory)
    result = evaluate_reclaim_readiness(inventory, now=NOW)
    assert result.ready
    assert result.reason == "balanced"
    assert result.workshops == 1
    assert result.seats == 2
    assert inventory == before


def test_missing_workshop_record_blocks():
    inventory = _inventory()
    inventory["workshops"] = []
    assert "workshop scope" in _reason(inventory)


def test_short_workshop_id_blocks_even_when_consistent():
    inventory = _inventory()
    inventory["scope"]["workshop_ids"] = [WORKSHOP[:8]]
    assert "full canonical UUID" in _reason(inventory)
    assert str(UUID(WORKSHOP)) == WORKSHOP


def test_stale_or_untrusted_completeness_blocks():
    inventory = _inventory()
    inventory["captured_at"] = (NOW - timedelta(minutes=31)).isoformat()
    assert "stale" in _reason(inventory)
    inventory = _inventory()
    inventory["scope"]["namespaces_complete"] = False
    assert "incomplete" in _reason(inventory)


def test_missing_or_extra_seat_blocks():
    inventory = _inventory()
    inventory["sessions"].pop()
    assert "seat count" in _reason(inventory)
    inventory = _inventory()
    inventory["sessions"][1]["seat_number"] = 1
    assert "seat numbering" in _reason(inventory)


def test_missing_or_orphan_namespace_blocks():
    inventory = _inventory()
    inventory["namespaces"].pop()
    assert "namespace" in _reason(inventory)
    inventory = _inventory()
    inventory["namespaces"].append(
        {
            "namespace": "launchpad-orphan",
            "cluster_ref": "arena",
            "workshop_id": WORKSHOP,
            "session_id": SESSION_1,
        }
    )
    assert "namespace" in _reason(inventory)


def test_cross_cluster_or_cross_workshop_ownership_blocks():
    inventory = _inventory()
    inventory["sessions"][0]["cluster_ref"] = "brutus"
    assert "cluster_ref" in _reason(inventory)
    inventory = _inventory()
    inventory["namespaces"][0]["workshop_id"] = SESSION_2
    assert "ownership" in _reason(inventory)


def test_reservation_missing_or_mismatched_blocks():
    inventory = _inventory()
    inventory["reservations"] = []
    assert "reservation" in _reason(inventory)
    inventory = _inventory()
    inventory["reservations"][0]["seat_count"] = 1
    assert "reservation" in _reason(inventory)


def test_legacy_workshop_without_reservation_is_supported():
    inventory = _inventory()
    inventory["workshops"][0]["reservation_id"] = None
    inventory["reservations"] = []
    assert evaluate_reclaim_readiness(inventory, now=NOW).ready


def test_active_workshop_and_session_are_supported():
    inventory = _inventory()
    inventory["workshops"][0]["state"] = "active"
    inventory["sessions"][0]["state"] = "active"
    assert evaluate_reclaim_readiness(inventory, now=NOW).ready


def test_cli_reads_only_and_reports_blocked(tmp_path, capsys):
    source = tmp_path / "inventory.json"
    source.write_text("{}", encoding="utf-8")
    assert main([str(source)]) == 2
    assert '"ready": false' in capsys.readouterr().out
    assert source.read_text(encoding="utf-8") == "{}"
    assert list(tmp_path.iterdir()) == [source]


def test_unknown_field_and_incomplete_cluster_coverage_block():
    inventory = _inventory()
    inventory["sessions"][0]["email"] = "not-allowed@example.test"
    assert "unexpected field" in _reason(inventory)
    inventory = _inventory()
    inventory["scope"]["cluster_refs"] = []
    assert "cluster coverage" in _reason(inventory)
