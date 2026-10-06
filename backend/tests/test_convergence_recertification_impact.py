from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
IMPACT = ROOT / "evidence/convergence/recertification-impact-20261006.yaml"
CANARY = ROOT / "evidence/convergence/platform-canary-20261006.yaml"
FULL_OVERLAY_CANARY = ROOT / "evidence/convergence/full-overlay-canary-20261006.yaml"
STAGING_WORKSHOP_PUBLIC_CANARY = (
    ROOT / "evidence/convergence/staging-workshop-public-canary-20261006.yaml"
)


def test_convergence_requires_a_platform_canary_without_overclaiming_lab_recertification() -> None:
    report = yaml.safe_load(IMPACT.read_text(encoding="utf-8"))
    decision = report["decision"]

    assert report["schema_version"] == (
        "launchpad.redhat.com/recertification-impact/v1"
    )
    assert decision["full_catalog_recertification_required"] is False
    assert decision["affected_lab_recertifications"] == []
    assert decision["platform_canary_required"] is True
    assert report["completed_proof"]["backend_non_local"]["passed"] == 2552
    assert report["completed_proof"]["requester_frontend"]["tests_passed"] == 81


def test_impact_report_keeps_automated_evidence_reuse_as_an_open_production_gate() -> None:
    report = yaml.safe_load(IMPACT.read_text(encoding="utf-8"))
    limitations = "\n".join(report["limitations"])
    remaining = "\n".join(report["remaining_gate"])

    assert "LP-S037" in limitations
    assert "Not every historical receipt binds" in limitations
    assert "zero residue" in remaining
    assert "targeted lab recertification" in remaining


def test_live_platform_canary_closes_the_selective_recertification_gate() -> None:
    proof = yaml.safe_load(CANARY.read_text(encoding="utf-8"))

    assert proof["schema_version"] == "launchpad.redhat.com/platform-canary/v1"
    assert proof["source"]["deployment_commit"] == "4e25830f"
    assert proof["scope"]["cluster"] == "flightpath"
    assert proof["preconditions"]["ready_nodes"] == 6
    assert proof["rollout"]["requester"]["result"] == "pass"
    assert proof["rollout"]["admin"]["result"] == "pass"
    assert proof["rollout"]["requester_ui"]["participant_catalog_items_visible"] == 21
    assert proof["rollout"]["requester_ui"]["compatibility_aliases_hidden"] == 2
    assert proof["rollout"]["requester_ui"]["order_links_resolve_to_declared_catalog_ids"] is True
    assert proof["canary"]["validation"]["checks_passed"] == 6
    assert proof["canary"]["validation"]["repeatability_score"] == 100
    assert proof["cleanup"]["namespace_count"] == 0
    assert proof["cleanup"]["route_count"] == 0
    assert proof["cleanup"]["rolebinding_count"] == 0
    assert proof["cleanup"]["argocd_application_count"] == 0
    assert proof["cleanup"]["active_session_count"] == 0
    assert proof["decision"]["platform_canary"] == "GREEN-live"
    assert proof["decision"]["blanket_lab_recertification_required"] is False
    assert proof["decision"]["targeted_lab_recertification_required"] == []


def test_full_overlay_canary_is_green_without_overclaiming_staging() -> None:
    proof = yaml.safe_load(FULL_OVERLAY_CANARY.read_text(encoding="utf-8"))

    assert proof["schema_version"] == "launchpad.redhat.com/full-overlay-canary/v1"
    assert proof["candidate"]["source_commit"] == "ae802b21"
    assert proof["candidate"]["rendered_resource_count"] == 76
    assert proof["preflight"]["selector_immutability_errors"] == 0
    assert proof["deployment"]["residual_diff"]["material_resources"] == 0
    assert proof["canary"]["validation"]["checks_passed"] == 6
    assert proof["canary"]["validation"]["repeatability_score"] == 100
    assert proof["cleanup"]["namespace_count"] == 0
    assert proof["cleanup"]["route_count"] == 0
    assert proof["cleanup"]["rolebinding_count"] == 0
    assert proof["cleanup"]["argocd_application_count"] == 0
    assert proof["decision"]["immutable_overlay_convergence"] == "GREEN-live"
    assert proof["decision"]["lifecycle_canary"] == "GREEN-live"
    assert proof["decision"]["staging_candidate_qualified"] is False
    assert proof["decision"]["live_workshop_order_and_capacity"] == "GREEN-live"
    assert proof["decision"]["authenticated_admin_bounded_action"] == "GREEN-live"
    assert proof["decision"]["public_participant_journey"] == "GREEN-live"
    assert proof["decision"]["namespace_isolation"] == "GREEN-live"
    assert proof["decision"]["workload_reclaim"] == "GREEN-live"
    assert len(proof["decision"]["remaining_qualification_gates"]) == 1


def test_staging_workshop_public_canary_records_the_last_gate_truthfully() -> None:
    proof = yaml.safe_load(STAGING_WORKSHOP_PUBLIC_CANARY.read_text(encoding="utf-8"))

    assert proof["schema_version"] == (
        "launchpad.redhat.com/staging-workshop-public-canary/v1"
    )
    assert proof["candidate"]["source_commit"] == "1adce64b"
    assert proof["candidate"]["backend_image"].endswith(
        "sha256:46eeb5f881369e843c03fe9e4c0a252798914332b1b3d429605f4beccdc3b053"
    )
    assert proof["candidate"]["signed_build"]["result"] == "pass"
    assert proof["internal_workshop"]["seats_ready"] == 1
    assert proof["defect_correction"]["focused_tests"]["passed"] == 108
    assert proof["defect_correction"]["deployed_retest"]["parent_workshop_status"] == "completed"
    assert proof["public_workshop"]["participant_journey"]["same_seat_recovery"] == "pass"
    assert proof["public_workshop"]["participant_journey"]["namespace_scoped_console"] == "pass"
    assert proof["public_workshop"]["authorization"] == {
        "assigned_namespace_list_pods": "allowed",
        "control_plane_namespace_list_pods": "denied",
        "cluster_nodes_get": "denied",
        "result": "pass",
    }
    assert proof["reclaim"]["parent_workshop_status"] == "completed"
    assert proof["reclaim"]["namespace_count"] == 0
    assert proof["reclaim"]["route_count"] == 0
    assert proof["reclaim"]["rolebinding_count"] == 0
    assert proof["reclaim"]["argocd_application_count"] == 0
    assert proof["identity_cleanup"]["controlled_activation"]["reconciled"] == 25
    assert proof["identity_cleanup"]["controlled_activation"]["cleanup_pending_after"] == 0
    assert proof["identity_cleanup"]["controlled_activation"]["second_run_reconciled"] == 0
    assert proof["identity_cleanup"]["scheduled_execution"]["succeeded"] is True
    assert proof["security_residue"]["openshift_oauth_access_tokens_for_disabled_identity"] == 0
    assert proof["security_residue"]["openshift_user_object_retained"] is False
    assert proof["security_residue"]["classification"] == "none"
    assert proof["decision"]["identity_cleanup"] == "GREEN-live"
    assert proof["decision"]["staging_candidate_qualified"] is True
    assert proof["decision"]["remaining_qualification_gates"] == []
