#!/usr/bin/env python3
"""Async Workload + Status Polling — TDD Red Phase"""

import sys
import time
import pytest


@pytest.fixture(autouse=True)
def setup(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
    monkeypatch.setenv("WORKLOAD_UNLOCK_HASH", "")


@pytest.fixture
def test_client():
    from fastapi.testclient import TestClient
    from router import app
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestAsyncRun:

    def test_run_returns_immediately_with_run_id(self, test_client):
        resp = test_client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "standby", "seed": 42
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data

    def test_run_returns_status_field(self, test_client):
        resp = test_client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "standby", "seed": 42
        })
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("running", "complete")


class TestStatusPolling:

    def test_status_endpoint_exists(self, test_client):
        resp = test_client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "standby", "seed": 42
        })
        run_id = resp.json()["run_id"]
        status_resp = test_client.get(f"/v1/workload/status/{run_id}")
        assert status_resp.status_code == 200

    def test_status_has_progress(self, test_client):
        resp = test_client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "standby", "seed": 42
        })
        run_id = resp.json()["run_id"]
        time.sleep(0.5)
        status_resp = test_client.get(f"/v1/workload/status/{run_id}")
        data = status_resp.json()
        assert "completed" in data
        assert "total" in data

    def test_status_has_results_list(self, test_client):
        resp = test_client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "standby", "seed": 42
        })
        run_id = resp.json()["run_id"]
        time.sleep(2)
        status_resp = test_client.get(f"/v1/workload/status/{run_id}")
        data = status_resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_completed_run_has_metrics(self, test_client):
        resp = test_client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "standby", "seed": 42
        })
        run_id = resp.json()["run_id"]
        for _ in range(20):
            time.sleep(0.3)
            status_resp = test_client.get(f"/v1/workload/status/{run_id}")
            data = status_resp.json()
            if data.get("status") == "complete":
                break
        assert data["status"] == "complete"
        assert "route_counts" in data
        assert "p50_latency_ms" in data

    def test_unknown_run_id_returns_404(self, test_client):
        resp = test_client.get("/v1/workload/status/nonexistent-id")
        assert resp.status_code == 404


class TestFrontendWiring:

    def test_client_has_workload_status(self, project_root):
        client = (project_root / "frontend" / "src" / "api" / "client.ts").read_text()
        assert "workloadStatus" in client
        assert "/v1/workload/status" in client
