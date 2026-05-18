#!/usr/bin/env python3
"""Agent Swarm — TDD tests for multi-level depth + scenarios"""

import sys
import time
import pytest


@pytest.fixture(autouse=True)
def setup(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")


# ─── EXISTING: Models ───

class TestSwarmModels:

    def test_swarm_agent_has_fields(self):
        from overdrive.swarm import SwarmAgent
        a = SwarmAgent(id="a1", name="Triage", role="classify", hardware_lane="xeon_eco", task_type="classification")
        assert a.id == "a1"
        assert a.hardware_lane == "xeon_eco"

    def test_incident_swarm_has_5_agents(self):
        from overdrive.swarm import INCIDENT_SWARM
        assert len(INCIDENT_SWARM["agents"]) >= 5

    def test_incident_swarm_has_3_waves(self):
        from overdrive.swarm import INCIDENT_SWARM
        assert len(INCIDENT_SWARM["waves"]) >= 3

    def test_wave_1_has_3_parallel_agents(self):
        from overdrive.swarm import INCIDENT_SWARM
        assert len(INCIDENT_SWARM["waves"][0]["agents"]) == 3

    def test_wave_2_depends_on_wave_1(self):
        from overdrive.swarm import INCIDENT_SWARM
        assert INCIDENT_SWARM["waves"][1]["depends_on"] == 0


# ─── EXISTING: Hardware ───

class TestSwarmHardware:

    def test_triage_on_xeon_eco(self):
        from overdrive.swarm import INCIDENT_SWARM
        agents = {a["id"]: a for a in INCIDENT_SWARM["agents"]}
        assert agents["triage"]["hardware_lane"] == "xeon_eco"

    def test_rca_on_gaudi(self):
        from overdrive.swarm import INCIDENT_SWARM
        agents = {a["id"]: a for a in INCIDENT_SWARM["agents"]}
        assert agents["rca"]["hardware_lane"] == "gaudi_overdrive"

    def test_reporter_on_gaudi(self):
        from overdrive.swarm import INCIDENT_SWARM
        agents = {a["id"]: a for a in INCIDENT_SWARM["agents"]}
        assert agents["reporter"]["hardware_lane"] == "gaudi_overdrive"


# ─── EXISTING: Execution ───

class TestSwarmExecution:

    def test_run_completes(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", seed=42)
        assert result["status"] == "completed"

    def test_all_agents_complete(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", seed=42)
        for agent_result in result["agent_results"]:
            assert agent_result["status"] == "done"

    def test_deterministic(self):
        from overdrive.swarm import run_swarm
        a = run_swarm("incident", seed=42)
        b = run_swarm("incident", seed=42)
        for ar, br in zip(a["agent_results"], b["agent_results"]):
            assert ar["output"] == br["output"]

    def test_has_timeline(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", seed=42)
        assert "timeline" in result
        assert len(result["timeline"]) >= 5

    def test_has_final_report(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", seed=42)
        assert "final_report" in result
        assert len(result["final_report"]) > 100


# ─── NEW: Scenarios ───

class TestSwarmScenarios:

    def test_security_audit_scenario_exists(self):
        from overdrive.swarm import SWARM_SCENARIOS
        assert "security_audit" in SWARM_SCENARIOS
        assert len(SWARM_SCENARIOS["security_audit"]["agents"]) >= 5

    def test_capacity_planning_scenario_exists(self):
        from overdrive.swarm import SWARM_SCENARIOS
        assert "capacity_planning" in SWARM_SCENARIOS
        assert len(SWARM_SCENARIOS["capacity_planning"]["agents"]) >= 5

    def test_security_audit_runs(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("security_audit", seed=42)
        assert result["status"] == "completed"
        assert result["scenario"] == "security_audit"

    def test_capacity_planning_runs(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("capacity_planning", seed=42)
        assert result["status"] == "completed"
        assert result["scenario"] == "capacity_planning"

    def test_security_audit_has_distinct_agents(self):
        from overdrive.swarm import SWARM_SCENARIOS
        agent_ids = [a["id"] for a in SWARM_SCENARIOS["security_audit"]["agents"]]
        assert "vuln_scanner" in agent_ids
        assert "compliance" in agent_ids

    def test_capacity_planning_has_distinct_agents(self):
        from overdrive.swarm import SWARM_SCENARIOS
        agent_ids = [a["id"] for a in SWARM_SCENARIOS["capacity_planning"]["agents"]]
        assert "resource_analyst" in agent_ids
        assert "growth_modeler" in agent_ids

    def test_each_scenario_deterministic(self):
        from overdrive.swarm import run_swarm
        for scenario in ["incident", "security_audit", "capacity_planning"]:
            a = run_swarm(scenario, seed=42)
            b = run_swarm(scenario, seed=42)
            assert len(a["agent_results"]) == len(b["agent_results"])
            for ar, br in zip(a["agent_results"], b["agent_results"]):
                assert ar["output"] == br["output"]


# ─── NEW: Depth Levels ───

class TestSwarmDepth:

    def test_triage_depth_has_3_agents(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", depth="triage", seed=42)
        assert len(result["agent_results"]) == 3

    def test_full_depth_has_5_agents(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", depth="full", seed=42)
        assert len(result["agent_results"]) == 5

    def test_deep_depth_has_8_agents(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", depth="deep", seed=42)
        assert len(result["agent_results"]) == 8

    def test_triage_has_2_waves(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", depth="triage", seed=42)
        assert result["wave_count"] == 2

    def test_full_has_3_waves(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", depth="full", seed=42)
        assert result["wave_count"] == 3

    def test_deep_has_4_waves(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", depth="deep", seed=42)
        assert result["wave_count"] == 4

    def test_deep_agents_have_correct_hardware(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", depth="deep", seed=42)
        agents = {r["agent_id"]: r for r in result["agent_results"]}
        assert "security_analyst" in agents
        assert "change_auditor" in agents
        assert "remediation_planner" in agents

    def test_depth_works_across_scenarios(self):
        from overdrive.swarm import run_swarm
        for scenario in ["incident", "security_audit", "capacity_planning"]:
            triage = run_swarm(scenario, depth="triage", seed=42)
            full = run_swarm(scenario, depth="full", seed=42)
            deep = run_swarm(scenario, depth="deep", seed=42)
            assert len(triage["agent_results"]) == 3
            assert len(full["agent_results"]) == 5
            assert len(deep["agent_results"]) == 8

    def test_triage_includes_reporter(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", depth="triage", seed=42)
        agent_ids = [r["agent_id"] for r in result["agent_results"]]
        assert "reporter" in agent_ids


# ─── NEW: Summary Metrics ───

class TestSwarmMetrics:

    def test_has_hw_utilization(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", seed=42)
        assert "hw_utilization" in result
        assert "xeon_eco" in result["hw_utilization"]
        assert "gaudi_overdrive" in result["hw_utilization"]

    def test_has_parallel_speedup(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", seed=42)
        assert "parallel_speedup" in result
        assert result["parallel_speedup"] > 1

    def test_hw_utilization_sums_to_100(self):
        from overdrive.swarm import run_swarm
        result = run_swarm("incident", seed=42)
        total = sum(result["hw_utilization"].values())
        assert abs(total - 100) < 1


# ─── EXISTING: API ───

class TestSwarmAPI:

    def test_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/swarm/run", json={"scenario": "incident", "seed": 42})
            assert resp.status_code == 200
            assert "run_id" in resp.json()

    def test_status_endpoint(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/swarm/run", json={"scenario": "incident", "seed": 42})
            run_id = resp.json()["run_id"]
            time.sleep(1)
            status = client.get(f"/v1/swarm/status/{run_id}")
            assert status.status_code == 200

    def test_depth_param_accepted(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/swarm/run", json={"scenario": "incident", "seed": 42, "depth": "deep"})
            assert resp.status_code == 200

    def test_platform_status_includes_swarm(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/v1/swarm/run", json={"scenario": "incident", "seed": 42})
            time.sleep(0.5)
            status = client.get("/v1/platform/status")
            data = status.json()
            has_swarm = any(r.get("type") == "swarm" for r in data.get("active_runs", []))
            swarm_completed = data.get("swarm_completed") is not None
            assert has_swarm or swarm_completed


# ─── EXISTING: Frontend ───

class TestFrontend:

    def test_page_exists(self, project_root):
        assert (project_root / "frontend" / "src" / "pages" / "SwarmDemo.tsx").exists()

    def test_route_exists(self, project_root):
        assert "/swarm" in (project_root / "frontend" / "src" / "App.tsx").read_text()

    def test_nav_exists(self, project_root):
        assert "/swarm" in (project_root / "frontend" / "src" / "components" / "AppLayout.tsx").read_text()

    def test_api_method(self, project_root):
        assert "swarm" in (project_root / "frontend" / "src" / "api" / "client.ts").read_text()
