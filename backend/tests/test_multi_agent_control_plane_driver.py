from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts/certify-multi-agent-via-control-plane.py"


def _driver_module():
    spec = importlib.util.spec_from_file_location("multi_agent_control_cert", DRIVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_remote_multi_agent_driver_uses_participant_pods_not_remote_exec():
    source = DRIVER.read_text()

    assert "service_account_name=\"showroom\"" in source
    assert "create_namespaced_pod" in source
    assert "read_namespaced_pod_log" in source
    assert "delete_namespaced_pod" in source
    assert '["oc", "exec"' not in source
    assert "oc exec" not in source


def test_remote_multi_agent_driver_proves_every_participant_component():
    source = DRIVER.read_text()

    for proof in (
        "/ready",
        "agents_discovered",
        "MCP tool data retrieved",
        "blocked by guardrails",
        "classification_status",
        "ui_workflow",
        "showroom_pages",
        "own_namespace_edit",
        "cross_namespace_read_denied",
        "node_list_denied",
        "runtime_secret_keys",
        "argocd_synced",
    ):
        assert proof in source


def test_remote_multi_agent_driver_is_cluster_pinned_and_secret_safe():
    source = DRIVER.read_text()

    assert "service._target_clients(args.cluster_id)" in source
    assert "workshop.cluster_ref != args.cluster_id" in source
    assert "session.cluster_ref != args.cluster_id" in source
    assert '"contains_plaintext_credentials": False' in source
    assert 'data["MODEL_API_KEY"]' not in source
    assert "base64.b64decode" not in source
    assert "print(token" not in source


def test_remote_multi_agent_driver_runs_a_bounded_concurrent_wave():
    source = DRIVER.read_text()

    assert "ThreadPoolExecutor" in source
    assert "--journey-concurrency" in source
    assert "len(targets)" in source
    assert '"seat_count"' in source
    assert '"passed"' in source


def test_remote_multi_agent_driver_parses_kubernetes_python_dict_log_shape():
    module = _driver_module()

    assert module._parse_last_json("{'passed': True, 'steps': 3}") == {
        "passed": True,
        "steps": 3,
    }
