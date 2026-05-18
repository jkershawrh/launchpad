#!/usr/bin/env python3
"""
Tests for POC Demo Applications

Validates that all three POC demos have the required structure,
import correctly, and define the expected entry points.
"""

import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def pocs_dir(project_root) -> Path:
    return project_root / "pocs"


class TestPOCStructure:
    """Test that all POC directories exist with required files"""

    @pytest.mark.parametrize("poc_name", [
        "enterprise-rag",
        "aiops-copilot",
        "governed-agent",
    ])
    def test_poc_directory_exists(self, pocs_dir, poc_name):
        assert (pocs_dir / poc_name).exists(), f"pocs/{poc_name}/ not found"

    @pytest.mark.parametrize("poc_name", [
        "enterprise-rag",
        "aiops-copilot",
        "governed-agent",
    ])
    def test_poc_has_app(self, pocs_dir, poc_name):
        assert (pocs_dir / poc_name / "app.py").exists(), \
            f"pocs/{poc_name}/app.py not found"

    @pytest.mark.parametrize("poc_name", [
        "enterprise-rag",
        "aiops-copilot",
        "governed-agent",
    ])
    def test_poc_has_readme(self, pocs_dir, poc_name):
        assert (pocs_dir / poc_name / "README.md").exists(), \
            f"pocs/{poc_name}/README.md not found"

    @pytest.mark.parametrize("poc_name", [
        "enterprise-rag",
        "aiops-copilot",
        "governed-agent",
    ])
    def test_poc_app_compiles(self, pocs_dir, poc_name):
        app_file = pocs_dir / poc_name / "app.py"
        if not app_file.exists():
            pytest.skip(f"{poc_name}/app.py not created yet")
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(app_file)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error in {poc_name}/app.py: {result.stderr}"


class TestEnterpriseRAG:
    """Test Enterprise RAG POC specifics"""

    def test_rag_has_pipeline_steps(self, pocs_dir):
        content = (pocs_dir / "enterprise-rag" / "app.py").read_text()
        assert 'step_embed' in content, "Should have embed step"
        assert 'step_search' in content, "Should have search step"
        assert 'step_rerank' in content, "Should have rerank step"
        assert 'step_generate' in content, "Should have generate step"

    def test_rag_calls_gateway(self, pocs_dir):
        content = (pocs_dir / "enterprise-rag" / "app.py").read_text()
        assert 'call_gateway' in content, "Should route through gateway"

    def test_rag_uses_multiple_tasks(self, pocs_dir):
        content = (pocs_dir / "enterprise-rag" / "app.py").read_text()
        assert '"embeddings"' in content, "Should use embeddings task"
        assert '"reranking"' in content, "Should use reranking task"
        assert '"completion"' in content, "Should use completion task"


class TestAIOPsCopilot:
    """Test AIOps Copilot POC specifics"""

    def test_aiops_has_pipeline_steps(self, pocs_dir):
        content = (pocs_dir / "aiops-copilot" / "app.py").read_text()
        assert 'step_classify' in content, "Should have classify step"
        assert 'step_correlate' in content, "Should have correlate step"
        assert 'step_generate_rca' in content, "Should have RCA generation step"
        assert 'step_governance' in content, "Should have governance step"

    def test_aiops_has_governance_policies(self, pocs_dir):
        content = (pocs_dir / "aiops-copilot" / "app.py").read_text()
        assert 'GOVERNANCE_POLICIES' in content, "Should define governance policies"

    def test_aiops_has_past_incidents(self, pocs_dir):
        content = (pocs_dir / "aiops-copilot" / "app.py").read_text()
        assert 'PAST_INCIDENTS' in content, "Should have sample incident data"


class TestGovernedAgent:
    """Test Governed Agent POC specifics"""

    def test_agent_has_pipeline_steps(self, pocs_dir):
        content = (pocs_dir / "governed-agent" / "app.py").read_text()
        assert 'step_classify_intent' in content, "Should have intent classification"
        assert 'step_risk_score' in content, "Should have risk scoring"
        assert 'step_plan' in content, "Should have plan generation"
        assert 'step_policy_check' in content, "Should have policy check"

    def test_agent_has_policy_rules(self, pocs_dir):
        content = (pocs_dir / "governed-agent" / "app.py").read_text()
        assert 'POLICY_RULES' in content, "Should define policy rules"

    def test_agent_has_deny_capability(self, pocs_dir):
        content = (pocs_dir / "governed-agent" / "app.py").read_text()
        assert '"deny"' in content, "Should be able to deny actions"
        assert '"escalate"' in content, "Should be able to escalate actions"
        assert '"allow"' in content, "Should be able to allow actions"

    def test_agent_produces_evidence(self, pocs_dir):
        content = (pocs_dir / "governed-agent" / "app.py").read_text()
        assert '"evidence"' in content, "Should produce evidence bundle"
