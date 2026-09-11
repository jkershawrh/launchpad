from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts/certify-multi-agent-seat.sh"


def test_multi_agent_live_driver_is_target_cluster_fail_closed_and_secret_safe():
    source = DRIVER.read_text()

    assert ': "${KUBECONFIG:?' in source
    assert 'expected_cluster="${2:?' in source
    assert 'command oc --kubeconfig "$KUBECONFIG" "$@"' in source
    assert ': "${CONTROL_KUBECONFIG:=$KUBECONFIG}"' in source
    assert 'command oc --kubeconfig "$CONTROL_KUBECONFIG" "$@"' in source
    assert 'actual_cluster' in source
    assert '!= "$expected_cluster"' in source
    assert "oc config use-context" not in source
    assert "jsonpath='{.data.MODEL_API_KEY}'" not in source
    assert "base64 -d" not in source
    assert "echo $AGENT_AUTH_TOKEN" not in source


def test_multi_agent_live_driver_proves_function_not_just_pod_status():
    source = DRIVER.read_text()

    assert 'result: "GREEN-live-internal-seat"' in source
    for proof in (
        "/ready",
        "agents_discovered",
        "multi-agent-ui",
        "showroom",
        "MCP tool data retrieved",
        "blocked by guardrails",
        "classification_status",
        "cross_namespace=DENIED",
        "node_list=DENIED",
        "contains_sensitive_values",
    ):
        assert proof in source


def test_multi_agent_driver_reads_central_argocd_from_the_control_plane():
    source = DRIVER.read_text()

    assert 'application="$(\n  control_oc get applications.argoproj.io' in source


def test_multi_agent_live_driver_proves_the_participant_terminal_scope():
    source = DRIVER.read_text()

    assert 'oc project -q' in source
    assert 'oc auth can-i create deployments.apps' in source
    assert 'oc get pods -n partner-ai-launchpad' in source
    assert 'oc get nodes' in source


def test_multi_agent_live_driver_does_not_pipe_curl_into_early_exit_grep():
    source = DRIVER.read_text()

    assert 'showroom_index="$(curl' in source
    assert "grep -q 'Build Multi-Agent AI Systems' <<<\"$showroom_index\"" in source
    assert "| grep -q 'Build Multi-Agent AI Systems'" not in source


def test_multi_agent_live_driver_can_bound_the_restart_heavy_policy_stage():
    source = DRIVER.read_text()

    assert "POLICY_CONCURRENCY" in source
    assert "POLICY_LOCK_DIR" in source
    assert "acquire_policy_slot" in source
    assert "release_policy_slot" in source
    assert 'stage="learner-policy-slot"' in source
