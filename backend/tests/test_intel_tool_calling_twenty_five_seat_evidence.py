"""Contract for the Arena 25-seat Tool Calling certification evidence."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/intel-tool-calling-twenty-five-seat-2026-09-04.json"


def test_twenty_five_seat_evidence_is_complete_and_does_not_overclaim_scope():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["schema_version"] == "1.0"
    assert evidence["outcome"] == "pass"
    assert evidence["scope"] == "internal-twenty-five-seat-workshop"
    assert evidence["cluster"] == "arena"
    assert evidence["catalog_item_id"] == "intel-llm-tool-calling"
    assert evidence["seat_count"] == 25
    assert evidence["public_access_certified"] is False
    assert evidence["three_concurrent_workshops_certified"] is False

    provisioning = evidence["provisioning"]
    assert provisioning["all_seats_ready"] is True
    assert provisioning["collective_ready_seconds"] <= 300
    assert provisioning["unique_session_count"] == 25
    assert provisioning["unique_namespace_count"] == 25
    assert provisioning["validated_pods"] == 25
    assert provisioning["healthy_synced_argocd_applications"] == 25

    participant = evidence["participant_validation"]
    assert participant["showroom_http_200"] == 25
    assert participant["guide_http_200"] == 25
    assert participant["resolved_model_urls"] == 25
    assert participant["default_project_matches_seat"] == 25
    assert participant["own_namespace_edit_allowed"] == 25
    assert participant["cross_seat_read_denied"] == 25
    assert participant["complete_tool_protocol"] == "pass"

    inference = evidence["concurrent_inference"]
    assert inference["successful_calls"] == 25
    assert inference["structured_tool_calls"] == 25
    assert inference["p95_seconds"] < 10

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


def test_tool_calling_driver_executes_the_complete_protocol_from_the_seat():
    driver = (ROOT / "scripts/certify-tool-calling-journey.sh").read_text()

    assert 'expected_cluster="${2:' in driver
    assert "actual_cluster" in driver
    assert '[[ "$actual_cluster" == "$expected_cluster" ]]' in driver
    assert "deploy/showroom -c terminal" in driver
    assert 'name:"get_weather"' in driver
    assert "tool_calls" in driver
    assert 'role:"tool"' in driver
    assert "temperature" in driver
    assert "complete-tool-protocol=true" in driver
