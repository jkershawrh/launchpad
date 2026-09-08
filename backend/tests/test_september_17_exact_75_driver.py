"""Contracts for the repeatable September 17 exact 75-seat live driver."""

import hashlib
import json

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts/certify-september-17-exact-75.sh"
RUN02_RED = (
    ROOT / "evidence/runs/september-17-exact75-run02-20260908-red.json"
)


def test_exact_75_driver_is_explicit_fail_closed_and_repeatable():
    source = DRIVER.read_text()

    assert ': "${KUBECONFIG:?' in source
    assert 'command oc --kubeconfig "$KUBECONFIG" "$@"' in source
    assert "oc config use-context" not in source
    assert "api.arena.fm2aihpcsed.com" in source
    assert "launchpad.redhat.com/workshop-id" in source
    assert '[[ "${#namespaces[@]}" -eq 25 ]]' in source
    assert '[[ ! -e "$result_dir" ]]' in source
    assert "contains_plaintext_credentials" in source
    assert "--request-timeout" in source
    assert "CORDON_ATTEMPTS" in source
    assert "MULTI_POLICY_CONCURRENCY" in source
    assert "MULTI_DEEP_CONCURRENCY" in source
    assert 'POLICY_CONCURRENCY="$MULTI_POLICY_CONCURRENCY"' in source
    assert 'POLICY_LOCK_DIR="$result_dir/policy-slots"' in source
    assert "run_multi_concurrent_wave" in source
    assert 'curl --config "$config"' in source
    assert "@base64d" in source
    assert "GREEN-live-participant-wave" in source
    assert "multi_concurrent_passed" in source
    assert "agent_receipt=" in source
    assert "grep '^{'" in source
    assert 'printf \'%s\' "$agent_receipt" | jq -r' in source


def test_exact_75_driver_runs_all_groups_concurrently_and_restores_node_guard():
    source = DRIVER.read_text()

    assert "certify-agent-201-via-control-plane.py" in source
    assert "certify-multi-agent-seat.sh" in source
    assert "certify-cpu-serving-rag.sh" in source
    assert "run_agent_201 >" in source
    assert "run_multi_agent >" in source
    assert "run_serve_llms >" in source
    assert "adm uncordon rhgnr1" in source
    assert "adm cordon rhgnr1" in source
    assert "wait \"$multi_pid\"" in source
    assert "recordon_rhgnr1" in source
    assert '"participants_started": 75' in source


def test_run02_red_receipt_distinguishes_client_routing_from_lab_failure():
    evidence = json.loads(RUN02_RED.read_text())

    assert evidence["schema"] == "launchpad.redhat.com/exact75-run/v1"
    assert evidence["result"] == "RED-client-path-unreachable"
    assert evidence["participants_started"] == 75
    assert evidence["participants_passed"] == 25
    assert evidence["groups"] == {
        "agent_201": {"cluster": "brutus", "passed": 25, "failed": 0},
        "multi_agent": {"cluster": "arena", "passed": 0, "failed": 25},
        "serve_llms": {"cluster": "arena", "passed": 0, "failed": 25},
    }
    assert evidence["client_path"]["arena_api_reachable"] is False
    assert evidence["client_path"]["local_subnet_overlap"] is True
    assert evidence["lab_failure_proven"] is False
    assert evidence["contains_plaintext_credentials"] is False


def test_run02_red_receipt_is_hash_verified():
    raw = RUN02_RED.read_bytes()
    expected = Path(f"{RUN02_RED}.sha256").read_text().split()[0]

    assert hashlib.sha256(raw).hexdigest() == expected
