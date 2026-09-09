from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/certify-arena-lifecycle-process-ha.sh"


def _script() -> str:
    return SCRIPT.read_text()


def test_certifier_is_explicitly_arena_scoped_and_fail_closed():
    script = _script()

    assert "--confirm-worker-deletion" in script
    assert "api.arena.fm2aihpcsed.com:6443" in script
    assert 'OC=(oc --kubeconfig "$KUBECONFIG_PATH")' in script
    assert "rhgnr1 must remain cordoned" in script
    assert "Exactly two lifecycle worker processes must be ready" in script
    assert "The certified 30-second worker lease is not deployed" in script
    assert "target_cluster:\"arena\"" in script
    assert "oc config use-context" not in script
    assert '"${OC[@]}" adm uncordon "$CORDONED_NODE"' in script


def test_certifier_faults_both_jobs_and_requires_fenced_zero_residue_recovery():
    script = _script()

    assert script.count('delete pod "$pod"') == 1
    assert "--force --grace-period=0 --wait=false" in script
    assert script.count("wait_for_takeover_completion") == 3
    assert '(( fence > initial_fence ))' in script
    assert "PROVISION_DELETED_POD" in script
    assert "RECLAIM_DELETED_POD" in script
    assert "NAMESPACE_RESIDUE" in script
    assert "ROUTE_RESIDUE" in script
    assert "ROLEBINDING_RESIDUE" in script
    assert "APPLICATION_RESIDUE" in script
    assert "wait_for_zero_residue" in script
    assert "queue_reclaim_best_effort" in script


def test_certifier_evidence_is_credential_free_and_hashed():
    script = _script()

    assert "GREEN-live-clean-process-ha" in script
    assert "contains_plaintext_credentials:false" in script
    assert "credential_values_logged:false" in script
    assert 'ADMIN_KEY=""' in script
    assert 'shasum -a 256 "$OUTPUT_PATH"' in script
    assert "public_certification_lab_preserved:true" in script


def test_certifier_supports_reversible_cross_node_process_takeover():
    script = _script()

    assert "--cross-node" in script
    assert "Cross-node mode requires two distinct worker nodes" in script
    assert 'cordon_owner_node "$PROVISION_INITIAL_OWNER"' in script
    assert 'cordon_owner_node "$RECLAIM_INITIAL_OWNER"' in script
    assert 'restore_cordoned_node' in script
    assert 'hold_showroom_application "$SESSION_NAMESPACE"' in script
    assert 'release_showroom_application_hold' in script
    assert "launchpad.redhat.com/certification-hold" in script
    assert "GREEN-live-cross-node-process-ha" in script
    assert 'cross_node_process_ha:"certified"' in script
    assert 'hard_node_failure:"not certified"' in script
