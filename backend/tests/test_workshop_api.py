"""
TDD: Workshop API endpoint tests.
RED first, then GREEN by building the router.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestWorkshopAPI:

    def test_create_workshop(self):
        """RED: POST /api/workshops should create a workshop and provision sessions."""
        resp = client.post("/workshops", json={
            "tenant_id": "redhat-summit",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": 3,
            "ttl": "4h",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["tenant_id"] == "redhat-summit"
        assert data["num_users"] == 3
        assert data["status"] == "ready"
        assert len(data["session_ids"]) == 3

    def test_get_workshop(self):
        """RED: GET /api/workshops/{id} should return workshop details."""
        create = client.post("/workshops", json={
            "tenant_id": "partner-test",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": 2,
            "ttl": "4h",
        })
        assert create.status_code == 201
        wid = create.json()["workshop_id"]

        resp = client.get(f"/workshops/{wid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workshop_id"] == wid
        assert len(data["session_ids"]) == 2

    def test_get_workshop_not_found(self):
        """GREEN: GET /api/workshops/{bad_id} should return 404."""
        resp = client.get("/workshops/nonexistent")
        assert resp.status_code == 404

    def test_list_workshops(self):
        """RED: GET /api/workshops should list all workshops."""
        resp = client.get("/workshops")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_delete_workshop(self):
        """RED: DELETE /api/workshops/{id} should reclaim all sessions."""
        create = client.post("/workshops", json={
            "tenant_id": "cleanup-test",
            "catalog_item_id": "inference-overdrive-quickstart",
            "num_users": 2,
            "ttl": "4h",
        })
        assert create.status_code == 201
        wid = create.json()["workshop_id"]

        resp = client.delete(f"/workshops/{wid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
