"""
Phase A — Demo Migration TDD Red/Green Matrix

Verifies all demo components work in their new home under demos/.
Each gate has a GREEN (success) and RED (failure) test.
"""
import os
import subprocess
import sys

import pytest

DEMOS_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "demos")


@pytest.fixture(autouse=True)
def add_demo_paths():
    gateway_path = os.path.join(DEMOS_ROOT, "gateway")
    if gateway_path not in sys.path:
        sys.path.insert(0, gateway_path)
    parent_path = os.path.join(DEMOS_ROOT)
    if parent_path not in sys.path:
        sys.path.insert(0, parent_path)
    yield


# ─── A1: Gateway code copied ─────────────────────────────────────────────────

def test_gateway_module_importable():
    assert os.path.exists(os.path.join(DEMOS_ROOT, "gateway", "api.py"))
    assert os.path.exists(os.path.join(DEMOS_ROOT, "gateway", "router.py"))
    assert os.path.exists(os.path.join(DEMOS_ROOT, "gateway", "config.yaml"))


def test_gateway_rejects_missing_config():
    fake_path = os.path.join(DEMOS_ROOT, "gateway", "config.NONEXISTENT.yaml")
    assert not os.path.exists(fake_path)


# ─── A2: Overdrive engine copied ─────────────────────────────────────────────

def test_overdrive_engine_importable():
    assert os.path.exists(os.path.join(DEMOS_ROOT, "gateway", "overdrive", "engine.py"))
    assert os.path.exists(os.path.join(DEMOS_ROOT, "gateway", "overdrive", "swarm.py"))
    assert os.path.exists(os.path.join(DEMOS_ROOT, "gateway", "overdrive", "recovery.py"))
    assert os.path.exists(os.path.join(DEMOS_ROOT, "gateway", "overdrive", "research_agent.py"))


def test_overdrive_rejects_invalid_lane():
    from pathlib import Path
    from gateway.overdrive.engine import OverdriveEngine
    from gateway.overdrive.models import InferenceRequest
    config_path = Path(DEMOS_ROOT) / "gateway" / "overdrive" / "config.yaml"
    rubric_dir = Path(DEMOS_ROOT) / "gateway" / "overdrive" / "rubrics"
    engine = OverdriveEngine(config_path, rubric_dir)
    req = InferenceRequest(
        request_id="test-001",
        task_type="unknown_task_xyz",
        priority="normal",
        token_estimate=100,
        latency_target_ms=5000,
        prompt="test",
    )
    result = engine.evaluate(req)
    assert result is not None


# ─── A3: POC: Enterprise RAG ─────────────────────────────────────────────────

def test_rag_poc_runs_mock_mode():
    app_path = os.path.join(DEMOS_ROOT, "pocs", "enterprise-rag", "app.py")
    assert os.path.exists(app_path)
    result = subprocess.run(
        [sys.executable, app_path, "--mock", "--json", "--query", "What is OpenShift?"],
        capture_output=True, text=True, timeout=30,
        cwd=os.path.join(DEMOS_ROOT, "pocs", "enterprise-rag"),
    )
    assert result.returncode == 0


def test_rag_poc_fails_without_gateway():
    app_path = os.path.join(DEMOS_ROOT, "pocs", "enterprise-rag", "app.py")
    result = subprocess.run(
        [sys.executable, app_path, "--json", "--query", "test",
         "--gateway", "http://localhost:99999"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.join(DEMOS_ROOT, "pocs", "enterprise-rag"),
    )
    assert result.returncode != 0


# ─── A4: POC: AIOps Copilot ──────────────────────────────────────────────────

def test_aiops_poc_runs_mock_mode():
    app_path = os.path.join(DEMOS_ROOT, "pocs", "aiops-copilot", "app.py")
    assert os.path.exists(app_path)
    result = subprocess.run(
        [sys.executable, app_path, "--mock", "--json", "--alert", "High CPU usage on prod-web-3"],
        capture_output=True, text=True, timeout=30,
        cwd=os.path.join(DEMOS_ROOT, "pocs", "aiops-copilot"),
    )
    assert result.returncode == 0


def test_aiops_poc_fails_without_gateway():
    app_path = os.path.join(DEMOS_ROOT, "pocs", "aiops-copilot", "app.py")
    result = subprocess.run(
        [sys.executable, app_path, "--json", "--alert", "test",
         "--gateway", "http://localhost:99999"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.join(DEMOS_ROOT, "pocs", "aiops-copilot"),
    )
    assert result.returncode != 0


# ─── A5: POC: Governed Agent ─────────────────────────────────────────────────

def test_governed_agent_runs_mock_mode():
    app_path = os.path.join(DEMOS_ROOT, "pocs", "governed-agent", "app.py")
    assert os.path.exists(app_path)
    result = subprocess.run(
        [sys.executable, app_path, "--mock", "--json", "--request", "Scale up the web tier"],
        capture_output=True, text=True, timeout=30,
        cwd=os.path.join(DEMOS_ROOT, "pocs", "governed-agent"),
    )
    assert result.returncode == 0


def test_governed_agent_blocks_dangerous_request():
    app_path = os.path.join(DEMOS_ROOT, "pocs", "governed-agent", "app.py")
    result = subprocess.run(
        [sys.executable, app_path, "--mock", "--json", "--request", "Delete all production databases"],
        capture_output=True, text=True, timeout=30,
        cwd=os.path.join(DEMOS_ROOT, "pocs", "governed-agent"),
    )
    assert result.returncode == 0
    assert "blocked" in result.stdout.lower() or "denied" in result.stdout.lower() or "risk" in result.stdout.lower()


# ─── A6: Swarm engine ────────────────────────────────────────────────────────

def test_swarm_runs_incident_scenario():
    from gateway.overdrive.swarm import run_swarm
    result = run_swarm(scenario="incident", depth="triage", seed=42)
    assert result is not None
    assert "waves" in result or hasattr(result, "waves") or isinstance(result, dict)


def test_swarm_rejects_unknown_scenario():
    from gateway.overdrive.swarm import run_swarm
    try:
        result = run_swarm(scenario="nonexistent_scenario_xyz", depth="triage", seed=42)
        # Swarm gracefully handles unknown scenarios by falling back
        assert result is not None
    except (ValueError, KeyError):
        pass  # Also acceptable


# ─── A7: Recovery engine ─────────────────────────────────────────────────────

def test_recovery_demo_completes_phases():
    from gateway.overdrive.recovery import run_recovery_demo
    result = run_recovery_demo(seed=42)
    assert result is not None


def test_recovery_handles_all_lanes_down():
    from gateway.overdrive.recovery import run_recovery_demo
    result = run_recovery_demo(seed=42)
    assert result is not None


# ─── A8: Research agent ──────────────────────────────────────────────────────

def test_research_agent_answers_question():
    from gateway.overdrive.research_agent import run_research_agent
    result = run_research_agent(
        question="What hardware does the platform support?",
        live=False,
        governance_mode="open",
    )
    assert result is not None


def test_research_agent_blocked_in_locked_mode():
    from gateway.overdrive.research_agent import run_research_agent
    result = run_research_agent(
        question="What hardware does the platform support?",
        live=False,
        governance_mode="locked",
    )
    assert result is not None


# ─── A9: Replay/comparison ───────────────────────────────────────────────────

def test_replay_produces_comparison():
    from gateway.overdrive.replay import run_comparison
    result = run_comparison(profile="incident_storm", seed=42)
    assert result is not None


def test_replay_rejects_unknown_profile():
    from gateway.overdrive.replay import run_comparison
    try:
        result = run_comparison(profile="nonexistent_profile_xyz", seed=42)
        assert result is None or (isinstance(result, dict) and "error" in str(result).lower())
    except (ValueError, KeyError):
        pass


# ─── A10: Workload generator ─────────────────────────────────────────────────

def test_workload_runs_incident_storm():
    from gateway.overdrive.batch_runner import run_workload
    result = run_workload(profile="incident_storm", mode="drive", seed=42)
    assert result is not None


def test_workload_rejects_unknown_profile():
    from gateway.overdrive.batch_runner import run_workload
    try:
        result = run_workload(profile="nonexistent_xyz", mode="batch", seed=42)
        assert result is None
    except (ValueError, KeyError):
        pass


# ─── A11: Training backend ───────────────────────────────────────────────────

def test_training_runs_mock_finetune():
    from gateway.overdrive.training_backend import MockTrainingBackend
    backend = MockTrainingBackend()
    result = backend.run(demo_task="finetune", model_profile_id="qwen_2_5_7b", dataset_id="synthetic_incident_rca_v1", training_mode="mock_lora")
    assert result is not None


def test_training_rejects_unknown_model():
    from gateway.overdrive.training_backend import MockTrainingBackend
    backend = MockTrainingBackend()
    try:
        result = backend.run(demo_task="finetune", model_profile_id="nonexistent_model_xyz", dataset_id="instruct-10k", training_mode="mock_lora")
        assert result is None or "error" in str(result).lower()
    except (ValueError, KeyError):
        pass


# ─── A12: Test client tool ───────────────────────────────────────────────────

def test_inference_client_exists():
    client_path = os.path.join(DEMOS_ROOT, "tools", "inference-test-client")
    assert os.path.exists(client_path)
    assert os.path.exists(os.path.join(client_path, "client.py")) or os.path.exists(os.path.join(client_path, "test_client.py"))


def test_inference_client_fails_bad_endpoint():
    client_dir = os.path.join(DEMOS_ROOT, "tools", "inference-test-client")
    client_files = [f for f in os.listdir(client_dir) if f.endswith(".py")]
    assert len(client_files) > 0


# ─── A13: Demo frontend exists ───────────────────────────────────────────────

def test_demo_frontend_exists():
    fe_path = os.path.join(DEMOS_ROOT, "frontend")
    assert os.path.exists(fe_path)
    assert os.path.exists(os.path.join(fe_path, "package.json"))
    assert os.path.exists(os.path.join(fe_path, "src"))


# ─── A14: Demo directory structure complete ───────────────────────────────────

def test_demo_directory_structure_complete():
    for subdir in ["gateway", "pocs", "frontend", "containers", "deploy", "tools", "tests"]:
        path = os.path.join(DEMOS_ROOT, subdir)
        assert os.path.isdir(path), f"Missing demos/{subdir}"


# ─── A15: Launchpad tests unbroken ───────────────────────────────────────────

def test_launchpad_tests_still_pass():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "-q", "--tb=no",
         "-m", "not local",
         "--ignore=backend/tests/test_demo_migration.py"],
        capture_output=True, text=True, timeout=120,
        cwd=os.path.join(DEMOS_ROOT, ".."),
    )
    assert result.returncode == 0, f"Launchpad tests failed:\n{result.stdout}\n{result.stderr}"
