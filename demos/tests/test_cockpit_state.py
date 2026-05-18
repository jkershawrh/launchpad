#!/usr/bin/env python3
"""Cockpit State Machine — TDD Red/Green

Tests the backend API behavior that the cockpit frontend depends on.
Each test validates one row of the test matrix.
"""

import sys
import time
import pytest


@pytest.fixture(autouse=True)
def setup(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
    monkeypatch.setenv("WORKLOAD_UNLOCK_HASH", "95bf2f017f4ae9491a96c8f1c17d4723e38b5dea388234a5929f6940e48ae4b3")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from router import app, _workload_runs
    _workload_runs.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    _workload_runs.clear()


def wait_for_completion(client, run_id, timeout=15):
    for _ in range(timeout * 5):
        time.sleep(0.2)
        r = client.get(f"/v1/workload/status/{run_id}")
        if r.json().get("status") in ("complete", "completed"):
            return r.json()
    return None


def get_platform(client):
    return client.get("/v1/platform/status").json()


# ----------------------------------------------------------------
# CORE: Platform status returns correct structure
# ----------------------------------------------------------------

class TestPlatformStatusStructure:

    def test_idle_returns_standby_mode(self, client):
        d = get_platform(client)
        assert d["aggregate"]["mode"] == "STANDBY"
        assert len(d["active_runs"]) == 0
        assert d["latest_completed"] is None

    def test_platform_returns_run_id_in_latest_completed(self, client):
        resp = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "standby", "seed": 42})
        run_id = resp.json()["run_id"]
        wait_for_completion(client, run_id)
        d = get_platform(client)
        assert d["latest_completed"] is not None
        assert d["latest_completed"]["run_id"] == run_id


# ----------------------------------------------------------------
# QUICK (5 reqs, standby)
# ----------------------------------------------------------------

class TestQuickLifecycle:

    def test_quick_sends_standby_creates_5(self, client):
        resp = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "standby", "seed": 42})
        run_id = resp.json()["run_id"]
        result = wait_for_completion(client, run_id)
        assert result is not None
        assert result.get("total_requests", result.get("total")) == 5

    def test_quick_completed_shows_5_in_platform(self, client):
        resp = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "standby", "seed": 42})
        run_id = resp.json()["run_id"]
        wait_for_completion(client, run_id)
        d = get_platform(client)
        lc = d["latest_completed"]
        assert lc["run_id"] == run_id
        assert lc["total_requests"] == 5
        total_routes = sum(lc["route_counts"].values())
        assert total_routes == 5


# ----------------------------------------------------------------
# STANDARD (25 reqs, drive)
# ----------------------------------------------------------------

class TestStandardLifecycle:

    def test_standard_sends_drive_creates_25(self, client):
        resp = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "drive", "seed": 42})
        run_id = resp.json()["run_id"]
        result = wait_for_completion(client, run_id)
        assert result is not None
        assert result.get("total_requests", result.get("total")) == 25

    def test_standard_after_quick_shows_25_not_5(self, client):
        # Run quick first
        r1 = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "standby", "seed": 42})
        wait_for_completion(client, r1.json()["run_id"])
        # Run standard
        r2 = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "drive", "seed": 99})
        run_id = r2.json()["run_id"]
        wait_for_completion(client, run_id)
        d = get_platform(client)
        lc = d["latest_completed"]
        assert lc["run_id"] == run_id, f"latest_completed should be standard run, got {lc['run_id']}"
        assert lc["total_requests"] == 25, f"Should show 25, got {lc['total_requests']}"


# ----------------------------------------------------------------
# EXTENDED (250 reqs, boost)
# ----------------------------------------------------------------

class TestExtendedLifecycle:

    def test_extended_without_unlock_returns_403(self, client):
        resp = client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "boost", "seed": 42,
            "live": True, "unlock_code": ""
        })
        assert resp.status_code == 403

    def test_extended_with_unlock_creates_250(self, client):
        resp = client.post("/v1/workload/run", json={
            "profile": "incident_storm", "mode": "boost", "seed": 42,
            "live": False, "unlock_code": "warpsp33d"
        })
        run_id = resp.json()["run_id"]
        result = wait_for_completion(client, run_id, timeout=30)
        assert result is not None
        assert result.get("total_requests", result.get("total")) == 250


# ----------------------------------------------------------------
# CROSS-SCALE: latest_completed always points to most recent
# ----------------------------------------------------------------

class TestCrossScaleIsolation:

    def test_quick_then_standard_latest_is_standard(self, client):
        r1 = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "standby", "seed": 1})
        wait_for_completion(client, r1.json()["run_id"])

        r2 = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "drive", "seed": 2})
        run_id_2 = r2.json()["run_id"]
        wait_for_completion(client, run_id_2)

        d = get_platform(client)
        assert d["latest_completed"]["run_id"] == run_id_2
        assert d["latest_completed"]["total_requests"] == 25

    def test_standard_then_quick_latest_is_quick(self, client):
        r1 = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "drive", "seed": 1})
        wait_for_completion(client, r1.json()["run_id"])

        r2 = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "standby", "seed": 2})
        run_id_2 = r2.json()["run_id"]
        wait_for_completion(client, run_id_2)

        d = get_platform(client)
        assert d["latest_completed"]["run_id"] == run_id_2
        assert d["latest_completed"]["total_requests"] == 5, f"Should be 5, got {d['latest_completed']['total_requests']}"

    def test_completed_at_ordering(self, client):
        """The run that FINISHES last should be latest_completed, regardless of start order."""
        r1 = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "drive", "seed": 10})
        wait_for_completion(client, r1.json()["run_id"])
        time.sleep(0.1)

        r2 = client.post("/v1/workload/run", json={"profile": "incident_storm", "mode": "standby", "seed": 20})
        run_id_2 = r2.json()["run_id"]
        wait_for_completion(client, run_id_2)

        d = get_platform(client)
        assert d["latest_completed"]["run_id"] == run_id_2


# ----------------------------------------------------------------
# FRONTEND STRUCTURE
# ----------------------------------------------------------------

class TestCockpitFrontendStructure:

    def test_cockpit_has_reducer_or_clean_state(self, project_root):
        content = (project_root / "frontend" / "src" / "pages" / "CockpitDashboard.tsx").read_text()
        assert "runId" in content, "Must track runId for isolation"
        assert "RESET" in content, "Must have reset action"
        assert "idle" in content, "Must have idle state"
        assert "running" in content, "Must have running state"

    def test_cockpit_checks_run_id_on_completion(self, project_root):
        content = (project_root / "frontend" / "src" / "pages" / "CockpitDashboard.tsx").read_text()
        assert "lcRunId" in content or "run_id" in content, "Must check run_id before accepting latest_completed data"
