import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/certify-arena-lifecycle-workshop-ha.sh"


def _script() -> str:
    return SCRIPT.read_text()


def test_workshop_certifier_is_explicitly_arena_scoped_and_fail_closed():
    script = _script()

    assert "--confirm-worker-deletion" in script
    assert "api.arena.fm2aihpcsed.com:6443" in script
    assert 'OC=(oc --kubeconfig "$KUBECONFIG_PATH")' in script
    assert "Exactly two lifecycle worker processes must be ready" in script
    assert "Workshop HA requires two distinct worker nodes" in script
    assert "Workshop HA requires hard topology spreading" in script
    assert "Workshop HA requires hostname pod anti-affinity" in script
    assert "Workshop HA requires a no-surge one-at-a-time rollout" in script
    assert "The certified 30-second worker lease is not deployed" in script
    assert '"target_cluster":"arena"' in script
    assert "oc config use-context" not in script


def test_workshop_certifier_bounds_seat_count_and_faults_both_aggregate_jobs():
    script = _script()

    assert "SEAT_COUNT must be 5 or 25" in script
    assert '"num_users":$seat_count' in script
    assert "PROVISION_WORKSHOP" in script
    assert "RECLAIM_WORKSHOP" in script
    assert 'wait_for_claim "$PROVISION_JOB_ID" provision_workshop' in script
    assert 'wait_for_claim "$RECLAIM_JOB_ID" reclaim_workshop' in script
    assert 'claimant_pod="$(owner_pod "$owner" 2>/dev/null || true)"' in script
    assert '&& -n "$claimant_pod"' in script
    assert 'local release_cordon_on_takeover="${4:-false}"' in script
    assert '[[ "$release_cordon_on_takeover" == "true" ]]' in script
    assert 'wait_for_takeover_completion "$PROVISION_JOB_ID" "$PROVISION_INITIAL_FENCE" "$PROVISION_DELETED_EPOCH" true' in script
    assert 'cordon_owner_node "$PROVISION_INITIAL_OWNER"' in script
    assert 'cordon_owner_node "$RECLAIM_INITIAL_OWNER"' in script
    assert script.count('delete_owner "$') == 2
    assert "--force --grace-period=0 --wait=false" in script
    assert '(( fence > initial_fence ))' in script
    assert "hold_showroom_applications" in script
    assert "release_showroom_application_holds" in script
    assert "launchpad.redhat.com/certification-hold" in script


def test_workshop_certifier_proves_every_seat_and_zero_aggregate_residue():
    script = _script()

    assert "verify_ready_workshop" in script
    assert "verify_seat_sessions" in script
    assert "unique_session_ids" in script
    assert "unique_namespaces" in script
    assert "showroom_http" in script
    assert "WORKSHOP_ID_LABEL" in script
    assert "NAMESPACE_RESIDUE" in script
    assert "ROUTE_RESIDUE" in script
    assert "ROLEBINDING_RESIDUE" in script
    assert "APPLICATION_RESIDUE" in script
    assert "wait_for_zero_workshop_residue" in script
    assert "public_certification_lab_preserved:true" in script


def test_workshop_certifier_is_reversible_credential_free_and_hashed():
    script = _script()

    assert "queue_reclaim_best_effort" in script
    assert '"${OC[@]}" adm uncordon "$CORDONED_NODE"' in script
    assert 'ADMIN_KEY=""' in script
    assert "contains_plaintext_credentials:false" in script
    assert "credential_values_logged:false" in script
    assert 'shasum -a 256 "$OUTPUT_PATH"' in script
    assert "GREEN-live-five-seat-cross-node-workshop-ha" in script
    assert 'hard_node_failure:"not certified"' in script
    assert 'twenty_five_seat_workshop_ha:(if $seat_count == 25 then "certified" else "not certified" end)' in script


def test_workshop_certifier_evidence_filter_compiles_with_jq():
    match = re.search(
        r"\n  '(\{\n    schema:.*?\n  \})' >\"\$OUTPUT_PATH\"",
        _script(),
        re.DOTALL,
    )
    assert match is not None

    text_args = [
        "evidence_id",
        "result",
        "commit",
        "image",
        "workshop_id",
        "catalog_item_id",
        "provision_job_id",
        "provision_deleted_pod",
        "provision_deleted_at",
        "provision_initial_node",
        "reclaim_job_id",
        "reclaim_deleted_pod",
        "reclaim_deleted_at",
        "reclaim_initial_node",
    ]
    json_args = {
        "seat_count": "5",
        "provision_initial": "{}",
        "provision_takeover": "{}",
        "reclaim_initial": "{}",
        "reclaim_takeover": "{}",
        "worker_nodes": "[]",
        "seat_proofs": "[]",
        "namespace_residue": "0",
        "route_residue": "0",
        "rolebinding_residue": "0",
        "application_residue": "0",
    }
    command = ["jq", "-n"]
    for name in text_args:
        command.extend(["--arg", name, "x"])
    for name, value in json_args.items():
        command.extend(["--argjson", name, value])

    result = subprocess.run(
        [*command, match.group(1)], capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr


def test_workshop_worker_spread_filter_counts_ready_pods_and_nodes():
    match = re.search(
        r"\| jq -r '(\[\.items\[\].*?\| @tsv)'\)",
        _script(),
    )
    assert match is not None
    pods = (
        '{"items":['
        '{"spec":{"nodeName":"gnr2"},"status":{"containerStatuses":[{"ready":true}]}},'
        '{"spec":{"nodeName":"rhgnr1"},"status":{"containerStatuses":[{"ready":true}]}}'
        "]}"
    )

    result = subprocess.run(
        ["jq", "-r", match.group(1)],
        input=pods,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2\t2"
