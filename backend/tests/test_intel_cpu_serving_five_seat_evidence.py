"""Contract for the Arena five-seat CPU Serving certification evidence."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/intel-cpu-serving-five-seat-2026-09-04.json"


def test_cpu_serving_five_seat_evidence_is_complete_and_scoped():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["schema_version"] == "1.0"
    assert evidence["outcome"] == "pass"
    assert evidence["scope"] == "internal-five-seat-workshop"
    assert evidence["cluster"] == "arena"
    assert evidence["catalog_item_id"] == "intel-llm-cpu-serving"
    assert evidence["seat_count"] == 5
    assert evidence["public_access_certified"] is False
    assert evidence["twenty_five_seat_certified"] is False

    provisioning = evidence["provisioning"]
    assert provisioning["all_seats_ready"] is True
    assert provisioning["collective_ready_seconds"] <= 120
    assert provisioning["unique_session_count"] == 5
    assert provisioning["unique_namespace_count"] == 5
    assert provisioning["showroom_pods_ready"] == 5
    assert provisioning["healthy_synced_argocd_applications"] == 5

    participant = evidence["participant_validation"]
    assert participant["showroom_http_200"] == 5
    assert participant["guide_http_200"] == 5
    assert participant["default_project_matches_seat"] == 5
    assert participant["own_namespace_edit_allowed"] == 5
    assert participant["cross_seat_read_denied"] == 5
    assert participant["anythingllm_deployments_ready"] == 5
    assert participant["anythingllm_http_200"] == 5
    assert participant["anythingllm_ping_http_200"] == 5
    assert participant["anythingllm_zero_restarts"] == 5
    assert participant["anythingllm_provider_valid"] == 5

    rag = evidence["concurrent_rag"]
    assert rag["successful_calls"] == 5
    assert rag["grounded_answers"] == 5
    assert rag["cited_documents"] == 5
    assert rag["p95_seconds"] < 10

    cleanup = evidence["cleanup"]
    assert cleanup["all_seats_reclaimed"] is True
    assert cleanup["completed_seconds"] <= 600
    assert cleanup["remaining_namespaces"] == 0
    assert cleanup["remaining_routes"] == 0
    assert cleanup["remaining_applications"] == 0
    assert cleanup["remaining_cross_namespace_rolebindings"] == 0

    assert all(
        row["status"] == "GREEN-live"
        for row in evidence["red_green_matrix"]
        if row["critical"]
    )
    assert evidence["gate_rubric"]["score"] == 100
    assert evidence["gate_rubric"]["required"] == 100


def test_cpu_serving_certification_driver_uses_the_participant_boundary():
    script = (ROOT / "scripts/certify-cpu-serving-seat.sh").read_text()
    rag_script = (ROOT / "scripts/certify-cpu-serving-rag.sh").read_text()

    assert 'actual_cluster="$(' in script
    assert 'expected_cluster="${2:?' in script
    assert 'actual_cluster" != "$expected_cluster' in script
    assert "refusing to mutate cluster" in script
    assert "deploy/showroom -c terminal" in script
    assert "anythingllm-openshift@sha256:" in script
    assert 'name: "rag"' in script
    assert 'haproxy.router.openshift.io/timeout' in script
    assert "GENERIC_OPEN_AI_BASE_PATH" in script
    assert "LAUNCHPAD_CURL_INTERFACE" in script
    assert "LAUNCHPAD_INGRESS_IP" in script
    assert 'actual_cluster="$(' in rag_script
    assert 'expected_cluster="${2:?' in rag_script
    assert 'actual_cluster" != "$expected_cluster' in rag_script
    assert "refusing to validate cluster" in rag_script
    assert "LAUNCHPAD_CURL_INTERFACE" in rag_script
    assert "LAUNCHPAD_INGRESS_IP" in rag_script
    assert "CERTIFICATION_RUN_ID" in rag_script
    assert "orion-leave-policy.txt" in rag_script
    assert 'contains("17")' in rag_script
    assert 'title == "orion-leave-policy.txt"' in rag_script
