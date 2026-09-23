"""The interim retained-lab evidence is internally consistent and secret-free."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.services.retained_inventory_evidence import validate_retained_inventory_evidence

EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "evidence/runs/pilot-closeout/retained-workshops-20260921.json"
)


@pytest.fixture
def snapshot():
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_retained_pilot_snapshot_is_consistent(snapshot):
    result = validate_retained_inventory_evidence(snapshot)
    assert result.workshops == 9
    assert result.seats == 270
    assert result.active_entitlements == 196


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["summary"].update(sessions_ready=269),
        lambda value: value["summary"].update(unclaimed_seats=75),
        lambda value: value["workshops"][0].update(active_entitlements=31),
        lambda value: value["workshops"][0].update(expires_at="2026-09-20T00:00:00Z"),
        lambda value: value["workshops"][0].update(cluster_ref="unobserved"),
        lambda value: value["summary"]["clusters"]["arena"].update(labeled_namespaces_present=59),
        lambda value: value["summary"].update(sessions_ready=True),
        lambda value: value["workshops"][1].update(
            workshop_id=value["workshops"][0]["workshop_id"]
        ),
        lambda value: value["workshops"][0].update(email="participant@example.org"),
        lambda value: value.update(not_a_reclaim_authorization=False),
    ],
)
def test_inconsistent_or_private_evidence_is_rejected(snapshot, change):
    changed = deepcopy(snapshot)
    change(changed)
    with pytest.raises(ValueError):
        validate_retained_inventory_evidence(changed)
