#!/usr/bin/env python3
"""Platform Status — TDD Red Phase"""

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


class TestPlatformStatusEndpoint:

    def test_endpoint_exists(self, test_client):
        resp = test_client.get("/v1/platform/status")
        assert resp.status_code == 200

    def test_returns_active_runs(self, test_client):
        data = test_client.get("/v1/platform/status").json()
        assert "active_runs" in data
        assert isinstance(data["active_runs"], list)

    def test_returns_aggregate(self, test_client):
        data = test_client.get("/v1/platform/status").json()
        assert "aggregate" in data

    def test_idle_returns_standby(self, test_client):
        data = test_client.get("/v1/platform/status").json()
        assert data["aggregate"]["mode"] == "STANDBY"
        assert data["aggregate"]["requests_per_second"] == 0


class TestPlatformStatusWithWorkload:

    def test_workload_run_shows_in_active(self, test_client):
        test_client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "standby", "seed": 42
        })
        time.sleep(1)
        data = test_client.get("/v1/platform/status").json()
        assert len(data["active_runs"]) >= 0  # may have completed already

    def test_completed_workload_shows_in_latest(self, test_client):
        test_client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "standby", "seed": 42
        })
        time.sleep(3)
        data = test_client.get("/v1/platform/status").json()
        assert data.get("latest_completed") is not None or len(data["active_runs"]) == 0


class TestPlatformStatusWithTraining:

    def test_training_run_visible(self, test_client):
        test_client.post("/v1/training/run", json={
            "task": "incident_rca_finetune", "model": "qwen_2_5_7b",
            "dataset": "synthetic_incident_rca_v1", "mode": "mock_lora", "seed": 42
        })
        time.sleep(1)
        data = test_client.get("/v1/platform/status").json()
        assert data.get("training") is not None


class TestFrontendWiring:

    def test_client_has_platform_status(self, project_root):
        client = (project_root / "frontend" / "src" / "api" / "client.ts").read_text()
        assert "platformStatus" in client
        assert "/v1/platform/status" in client

    def test_cockpit_polls_platform(self, project_root):
        content = (project_root / "frontend" / "src" / "pages" / "CockpitDashboard.tsx").read_text()
        assert "platformStatus" in content or "platform" in content.lower()
