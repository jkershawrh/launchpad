from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts/certify-agent-201-via-control-plane.py"


def test_remote_certifier_uses_persisted_cluster_client_without_kubeconfig_or_exec():
    source = DRIVER.read_text()

    assert 'service._target_clients(args.cluster_id)' in source
    assert "create_namespaced_pod" in source
    assert "read_namespaced_pod_log" in source
    assert 'service_account_name="showroom"' in source
    assert "connect_get_namespaced_pod_exec" not in source
    assert "KUBECONFIG" not in source
    assert "config.load_kube_config" not in source


def test_remote_certifier_runs_the_documented_agent_201_journey():
    source = DRIVER.read_text()

    for expected in (
        "intel_hardware_lookup",
        "openshift_capabilities",
        "reference_architectures",
        "solution-agent",
        "solution-ui",
        "ADVISOR_MODEL",
    ):
        assert expected in source


def test_remote_certifier_proves_participant_scope_and_sanitizes_evidence():
    source = DRIVER.read_text()

    assert "ast.literal_eval(output)" in source
    assert '"failure_stage"' in source
    assert "tools_health" in source
    assert "model_request" in source
    assert 'oc project "$NAMESPACE"' not in source
    assert source.count('-n "$NAMESPACE"') >= 8
    assert "cross_namespace_read_denied" in source
    assert "node_list_denied" in source
    assert '"contains_plaintext_credentials": False' in source
    assert "MAAS_API_KEY}" not in source
