from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from app.api import deps
from app.main import app
from app.services.event_capacity import (
    EventCapacityMatrixUnavailableError,
    FileEventCapacityProvider,
)
from fastapi.testclient import TestClient


def _matrix() -> dict:
    return {
        "schema_version": "launchpad.intel.com/event-capacity/v1",
        "matrix_id": "pilot-matrix-2026-09-18",
        "approved_by": ["event-owner", "technical-owner"],
        "approved_at": "2026-09-18T12:00:00Z",
        "evidence_refs": ["evidence/certification/pilot-matrix.json"],
        "clusters": [
            {
                "cluster_id": "arena",
                "enabled": True,
                "priority": 10,
                "exposure_policies": ["internal", "public_code"],
                "capabilities": ["cpu", "model-endpoint"],
                "certified_seats": 30,
                "dr_reserved_seats": 0,
                "uncertified_seats": 0,
                "resource_capacity": {
                    "seats": 30,
                    "cpu_millicores": 30000,
                    "memory_mib": 60000,
                    "pods": 90,
                    "storage_gib": 300,
                    "routes": 90,
                    "model_slots": 30,
                },
                "catalogs": [
                    {
                        "catalog_id": "intel-llm-cpu-serving",
                        "catalog_release": "v1",
                        "certified_seats": 30,
                        "resources_per_seat": {
                            "seats": 1,
                            "cpu_millicores": 1000,
                            "memory_mib": 2000,
                            "pods": 3,
                            "storage_gib": 10,
                            "routes": 3,
                            "model_slots": 1,
                        },
                    }
                ],
            }
        ],
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def test_provider_loads_jointly_approved_versioned_matrix(tmp_path):
    supply = FileEventCapacityProvider(_write(tmp_path / "matrix.yaml", _matrix())).load()

    assert supply.matrix_id == "pilot-matrix-2026-09-18"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", supply.matrix_digest)
    assert len(supply.clusters) == 1
    assert supply.clusters[0].cluster_id == "arena"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("approved_by", ["only-one-owner"], "at least 2 items"),
        ("evidence_refs", [], "at least 1 item"),
        ("schema_version", "v0", "launchpad.intel.com/event-capacity/v1"),
        (
            "evidence_refs",
            ["evidence/proof.json", "evidence/proof.json"],
            "evidence references must be unique",
        ),
        ("approved_at", "2026-09-18T12:00:00", "must include a timezone"),
    ],
)
def test_provider_rejects_unapproved_or_unversioned_matrix(
    tmp_path, field, value, message
):
    payload = _matrix()
    payload[field] = value
    path = _write(tmp_path / "matrix.yaml", payload)

    with pytest.raises(EventCapacityMatrixUnavailableError, match=message):
        FileEventCapacityProvider(path).load()


def test_provider_rejects_missing_configured_file(tmp_path):
    with pytest.raises(EventCapacityMatrixUnavailableError, match="does not exist"):
        FileEventCapacityProvider(tmp_path / "missing.yaml").load()


def test_provider_rejects_matrix_without_resource_evidence(tmp_path):
    payload = _matrix()
    payload["clusters"][0].pop("resource_capacity")
    path = _write(tmp_path / "matrix.yaml", payload)

    with pytest.raises(
        EventCapacityMatrixUnavailableError,
        match="requires a certified resource capacity",
    ):
        FileEventCapacityProvider(path).load()


def test_unconfigured_dependency_remains_zero_capacity(monkeypatch):
    monkeypatch.delenv("EVENT_CAPACITY_MATRIX_FILE", raising=False)

    supply = deps.get_event_capacity_supply()

    assert supply.matrix_id == "unconfigured"
    assert supply.matrix_digest == "unconfigured"
    assert supply.clusters == []


def test_configured_invalid_matrix_fails_api_closed_with_503(tmp_path, monkeypatch):
    path = _write(tmp_path / "matrix.yaml", {"not": "a matrix"})
    monkeypatch.setenv("EVENT_CAPACITY_MATRIX_FILE", str(path))

    response = TestClient(app).post(
        "/api/v1/events/capacity-preview",
        json={
            "event_id": "provider-fail-closed",
            "name": "Provider fail closed",
            "owner": "event-owner",
            "technical_approver": "technical-owner",
            "exposure_policy": "internal",
            "placement_policy": "single_cluster_per_workshop",
            "cohorts": [
                {"cohort_id": "wave-1", "participants": 1, "lab_refs": ["lab"]}
            ],
            "labs": [
                {
                    "lab_ref": "lab",
                    "catalog_id": "catalog",
                    "catalog_release": "v1",
                }
            ],
            "retention": {"hours": 1, "starts_from": "cohort_start"},
            "approval": {
                "event_owner_approved": True,
                "technical_approver_approved": True,
                "approved_seat_environments": 1,
                "approved_retention_hours": 1,
            },
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Certified event capacity is unavailable"
