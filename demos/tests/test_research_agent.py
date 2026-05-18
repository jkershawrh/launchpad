#!/usr/bin/env python3
"""RAG Research Agent — TDD Red Phase"""

import sys
import time
import pytest


@pytest.fixture(autouse=True)
def setup(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")


class TestAgentModule:

    def test_importable(self):
        from overdrive.research_agent import run_research_agent
        assert run_research_agent is not None

    def test_has_knowledge_base(self):
        from overdrive.research_agent import KNOWLEDGE_BASE
        assert isinstance(KNOWLEDGE_BASE, list)
        assert len(KNOWLEDGE_BASE) >= 10


class TestAgentSteps:

    def test_decompose_returns_sub_queries(self):
        from overdrive.research_agent import step_decompose
        result = step_decompose("How does routing work on Xeon 6 vs Gaudi?")
        assert "sub_queries" in result
        assert isinstance(result["sub_queries"], list)
        assert len(result["sub_queries"]) >= 2

    def test_search_returns_documents(self):
        from overdrive.research_agent import step_search
        result = step_search("Xeon 6 inference routing")
        assert "documents" in result
        assert isinstance(result["documents"], list)
        assert len(result["documents"]) >= 1

    def test_rerank_returns_scored_documents(self):
        from overdrive.research_agent import step_rerank
        docs = [{"title": "Test", "content": "Some content", "score": 0.5}]
        result = step_rerank("test query", docs)
        assert "ranked_documents" in result
        assert isinstance(result["ranked_documents"], list)

    def test_synthesize_returns_answer(self):
        from overdrive.research_agent import step_synthesize
        docs = [{"title": "Test Doc", "content": "Xeon 6 handles classification."}]
        result = step_synthesize("How does routing work?", ["sub query 1"], docs)
        assert "answer" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    def test_governance_check_returns_decision(self):
        from overdrive.research_agent import step_governance
        result = step_governance("This is a safe answer about routing.")
        assert "decision" in result
        assert result["decision"] in ("pass", "escalate", "fail")


class TestGovernanceModes:

    def test_open_mode_no_approval_needed(self):
        from overdrive.research_agent import get_steps_requiring_approval
        steps = get_steps_requiring_approval("open")
        assert len(steps) == 0

    def test_supervised_requires_synthesis_approval(self):
        from overdrive.research_agent import get_steps_requiring_approval
        steps = get_steps_requiring_approval("supervised")
        assert "synthesize" in steps

    def test_locked_requires_all_approval(self):
        from overdrive.research_agent import get_steps_requiring_approval
        steps = get_steps_requiring_approval("locked")
        assert len(steps) >= 4


class TestAgentOrchestration:

    def test_run_returns_result_dict(self):
        from overdrive.research_agent import run_research_agent
        run_state = {"run_id": "test-001", "status": "running", "steps": []}
        result = run_research_agent(
            question="What is hardware-aware routing?",
            governance_mode="open",
            run_state=run_state,
        )
        assert isinstance(result, dict)
        assert "answer" in result

    def test_run_populates_steps(self):
        from overdrive.research_agent import run_research_agent
        run_state = {"run_id": "test-002", "status": "running", "steps": []}
        run_research_agent(
            question="How does Xeon 6 handle embeddings?",
            governance_mode="open",
            run_state=run_state,
        )
        assert len(run_state["steps"]) >= 4

    def test_each_step_has_required_fields(self):
        from overdrive.research_agent import run_research_agent
        run_state = {"run_id": "test-003", "status": "running", "steps": []}
        run_research_agent(
            question="Explain Gaudi throughput advantages.",
            governance_mode="open",
            run_state=run_state,
        )
        for step in run_state["steps"]:
            assert "name" in step
            assert "status" in step
            assert "hw" in step
            assert "output" in step

    def test_step_has_routing_reason(self):
        from overdrive.research_agent import run_research_agent
        run_state = {"run_id": "test-004", "status": "running", "steps": []}
        run_research_agent(
            question="What is tokenization?",
            governance_mode="open",
            run_state=run_state,
        )
        for step in run_state["steps"]:
            assert "routing_reason" in step


class TestAPIEndpoints:

    def test_research_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/agent/research", json={
                "question": "What is routing?", "governance_mode": "open"
            })
            assert resp.status_code == 200
            assert "run_id" in resp.json()

    def test_status_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            start = client.post("/v1/agent/research", json={
                "question": "What is routing?", "governance_mode": "open"
            })
            run_id = start.json()["run_id"]
            time.sleep(1)
            status = client.get(f"/v1/agent/status/{run_id}")
            assert status.status_code == 200

    def test_approve_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/v1/agent/approve/fake-id/synthesize")
            assert resp.status_code in (200, 404)


class TestFrontendWiring:

    def test_page_exists(self, project_root):
        assert (project_root / "frontend" / "src" / "pages" / "ResearchAgent.tsx").exists()

    def test_route_exists(self, project_root):
        app = (project_root / "frontend" / "src" / "App.tsx").read_text()
        assert "/agent" in app

    def test_nav_exists(self, project_root):
        layout = (project_root / "frontend" / "src" / "components" / "AppLayout.tsx").read_text()
        assert "/agent" in layout

    def test_api_methods(self, project_root):
        client = (project_root / "frontend" / "src" / "api" / "client.ts").read_text()
        assert "agentResearch" in client or "agent" in client
        assert "/v1/agent" in client
