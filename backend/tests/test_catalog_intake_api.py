from __future__ import annotations

import pytest
from app.api.deps import catalog_adapter, catalog_intake_submission_service
from app.auth.oauth import User, require_admin
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_draft_intakes():
    catalog_intake_submission_service.clear()
    app.dependency_overrides[require_admin] = lambda: User(
        username="intake-admin",
        is_admin=True,
    )
    yield
    catalog_intake_submission_service.clear()
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
def client():
    return TestClient(app)


def _payload() -> dict:
    return {
        "catalog_item_id": "example-agent-lab",
        "display_name": "Example Agent Lab",
        "repository_url": "https://github.com/example/agent-lab.git",
        "revision": "b" * 40,
        "owner": "solution-owner@example.com",
        "audience": ["intel-sellers"],
        "duration_hours": 4,
        "lab_type": "guided_build",
        "expected_scale": 25,
    }


def test_admin_submits_and_reads_draft_without_editing_live_catalog(client):
    before = [item.model_dump() for item in catalog_adapter.list_items()]

    response = client.post("/api/v1/admin/catalog-intakes", json=_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "draft"
    assert body["orderable"] is False
    assert body["promotion_eligible"] is False
    assert body["defaults"] == {
        "exposure_policies": ["internal"],
        "maximum_seats": 1,
    }
    assert body["supported_targets"] == []
    assert body["evidence"]["status"] == "not-run"
    assert body["requested"]["owner"] == "solution-owner@example.com"
    assert body["requested"]["audience"] == ["intel-sellers"]
    assert body["requested"]["duration_hours"] == 4
    assert body["requested"]["lab_type"] == "guided_build"
    assert body["requested"]["expected_scale"] == 25
    assert [item.model_dump() for item in catalog_adapter.list_items()] == before

    fetched = client.get(f"/api/v1/admin/catalog-intakes/{body['intake_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body
    listed = client.get("/api/v1/admin/catalog-intakes")
    assert listed.status_code == 200
    assert listed.json() == [body]


def test_admin_submission_is_idempotent_and_rejects_promotion_inputs(client):
    first = client.post("/api/v1/admin/catalog-intakes", json=_payload())
    second = client.post("/api/v1/admin/catalog-intakes", json=_payload())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert len(client.get("/api/v1/admin/catalog-intakes").json()) == 1

    unsafe = _payload()
    unsafe.update({"status": "active", "exposure_policy": "public_code"})
    rejected = client.post("/api/v1/admin/catalog-intakes", json=unsafe)
    assert rejected.status_code == 422


def test_admin_submission_rejects_mutable_revision_and_missing_intake(client):
    payload = _payload()
    payload["revision"] = "main"

    rejected = client.post("/api/v1/admin/catalog-intakes", json=payload)

    assert rejected.status_code == 422
    assert "immutable 40-character Git SHA" in rejected.text
    missing = client.get("/api/v1/admin/catalog-intakes/intake-missing")
    assert missing.status_code == 404


def test_catalog_intake_pipeline_is_read_only_and_fail_closed(client):
    created = client.post("/api/v1/admin/catalog-intakes", json=_payload())
    intake_id = created.json()["intake_id"]

    response = client.get(f"/api/v1/admin/catalog-intakes/{intake_id}/pipeline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_stage"] == "submitted"
    assert payload["orderable"] is False
    assert payload["promotion_eligible"] is False
    assert payload["actions"] == {
        "approve_source": False,
        "run_discovery": False,
        "generate_draft": False,
        "run_one_seat_certification": False,
        "request_review": False,
        "promote": False,
    }

    approval = client.post(
        f"/api/v1/admin/catalog-intakes/{intake_id}/source-approval"
    )
    discovery = client.post(f"/api/v1/admin/catalog-intakes/{intake_id}/discovery")
    assert approval.status_code == 409
    assert "durable intake storage" in approval.text
    assert discovery.status_code == 409
    assert "not available" in discovery.text
