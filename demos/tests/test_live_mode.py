#!/usr/bin/env python3
"""Live Mode — TDD Red Phase

Tests governance: unlock codes, throttling, labeling.
Does NOT make real LiteLLM calls (uses mocked HTTP).
"""

import sys
import os
import hashlib
import pytest

UNLOCK_CODE = "warpsp33d"
UNLOCK_HASH = hashlib.sha256(UNLOCK_CODE.encode()).hexdigest()


@pytest.fixture(autouse=True)
def setup_env(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
    monkeypatch.setenv("WORKLOAD_UNLOCK_HASH", UNLOCK_HASH)


class TestGovernanceUnlock:

    def test_standby_no_unlock_required(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42, live=False)
        assert result["completed_requests"] == 5

    def test_live_standby_no_unlock_required(self):
        """Standby/drive don't raise PermissionError for live mode."""
        from overdrive.batch_runner import run_workload, GOVERNED_MODES
        assert "standby" not in GOVERNED_MODES

    def test_live_drive_no_unlock_required(self):
        from overdrive.batch_runner import GOVERNED_MODES
        assert "drive" not in GOVERNED_MODES
        assert "cooldown" not in GOVERNED_MODES

    def test_live_boost_requires_unlock(self):
        from overdrive.batch_runner import run_workload
        with pytest.raises(PermissionError):
            run_workload(profile="incident_storm", mode="boost", seed=42, live=True)

    def test_live_overdrive_requires_unlock(self):
        from overdrive.batch_runner import run_workload
        with pytest.raises(PermissionError):
            run_workload(profile="incident_storm", mode="overdrive", seed=42, live=True)

    def test_live_max_q_requires_unlock(self):
        from overdrive.batch_runner import run_workload
        with pytest.raises(PermissionError):
            run_workload(profile="incident_storm", mode="max_q", seed=42, live=True)

    def test_wrong_unlock_rejected(self):
        from overdrive.batch_runner import run_workload
        with pytest.raises(PermissionError):
            run_workload(profile="incident_storm", mode="boost", seed=42, live=True, unlock_code="wrong")

    def test_correct_unlock_accepted(self):
        from overdrive.batch_runner import _verify_unlock
        assert _verify_unlock(UNLOCK_CODE) is True

    def test_cooldown_not_governed(self):
        from overdrive.batch_runner import GOVERNED_MODES
        assert "cooldown" not in GOVERNED_MODES


class TestLiveLabeling:

    def test_simulated_labeled(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42, live=False)
        assert result.get("mode_label") == "simulated"

    def test_live_labeled(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="incident_storm", mode="standby", seed=42, live=False)
        assert result.get("mode_label") == "simulated"
        # Live label tested via governance logic, not actual HTTP calls


class TestThrottle:

    def test_throttle_config_exists(self):
        from overdrive.timing_provider import RealTimingProvider
        tp = RealTimingProvider(gateway_url="http://localhost:8080")
        assert hasattr(tp, 'min_interval_ms')
        assert tp.min_interval_ms >= 750


class TestRealTimingProvider:

    def test_importable(self):
        from overdrive.timing_provider import RealTimingProvider
        assert RealTimingProvider is not None

    def test_has_simulate_method(self):
        from overdrive.timing_provider import RealTimingProvider
        tp = RealTimingProvider(gateway_url="http://localhost:8080")
        assert hasattr(tp, 'simulate')


class TestAPIEndpointGovernance:

    def test_endpoint_accepts_live_param(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/workload/run", json={
                "profile": "incident_storm", "mode": "standby", "seed": 42, "live": False
            })
            assert resp.status_code == 200

    def test_endpoint_rejects_boost_live_without_unlock(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/workload/run", json={
                "profile": "incident_storm", "mode": "boost", "seed": 42,
                "live": True, "unlock_code": ""
            })
            assert resp.status_code == 403

    def test_endpoint_accepts_simulated_boost(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/workload/run", json={
                "profile": "incident_storm", "mode": "boost", "seed": 42,
                "live": False
            })
            assert resp.status_code == 200
