"""Contract for the revised September 17 agentic workshop release gate."""

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "evidence/september-17-two-cluster-three-workshop-readiness-2026-09-07.json"
RUNBOOK = ROOT / "docs/september-17-agentic-three-workshop-readiness.md"
READINESS_CHECKSUM = READINESS.with_suffix(".json.sha256")
CONTRACT_EVIDENCE = ROOT / "evidence/september-17-multicluster-event-contract-test-2026-09-07.json"
TWO_CLUSTER_PREFLIGHT = ROOT / "evidence/runs/september-17-two-cluster-preflight-20260907-red.json"


def test_event_readiness_manifest_keeps_the_exact_workshop_target_and_budget():
    readiness = json.loads(READINESS.read_text())

    assert readiness["schema"] == "launchpad.redhat.com/event-readiness/v4"
    assert readiness["event_date"] == "2026-09-17"
    assert readiness["deployment_scope"] == "arena-brutus-fleet"
    assert readiness["candidate_cluster_targets"] == {
        "multi-agent-quickstart": "arena",
        "intel-llm-cpu-serving": "arena",
        "intel-xeon6-agent-201": "brutus",
    }
    assert readiness["candidate_cluster_workshop_counts"] == {
        "arena": 2,
        "brutus": 1,
    }
    assert readiness["workshop_affinity"] == "one-workshop-one-cluster"
    assert readiness["seat_splitting_allowed"] is False
    assert readiness["provisioning_mode"] == "staggered-retained"
    assert readiness["concurrent_participant_seats"] == 75

    workshops = readiness["workshops"]
    assert [workshop["catalog_item_id"] for workshop in workshops] == [
        "multi-agent-quickstart",
        "intel-llm-cpu-serving",
        "intel-xeon6-agent-201",
    ]
    assert all(workshop["seat_count"] == 25 for workshop in workshops)
    assert workshops[0]["release_status"] == "GREEN-live-25-x3-internal"
    assert workshops[1]["release_status"] == ("GREEN-live-five-seat-current-and-25-historical")
    assert workshops[2]["catalog_version"] == "1.0.2"
    assert workshops[2]["release_status"] == "GREEN-live-25-once-internal"
    assert [workshop["candidate_cluster_id"] for workshop in workshops] == [
        "arena",
        "arena",
        "brutus",
    ]

    declared = readiness["declared_event_reservation"]
    assert declared == {
        "cpu_millicores": 57000,
        "memory_mib": 111200,
        "pod_slots": 175,
        "storage_gib_minimum": 0,
    }
    protected = readiness["admission_target_with_twenty_percent_headroom"]
    assert protected == {
        "cpu_millicores": 68400,
        "memory_mib": 133440,
        "pod_slots": 210,
        "storage_gib_minimum": 0,
    }

    assert readiness["public_access_certified"] is False
    assert readiness["overall_status"] == "RED"
    assert readiness["next_gate"] == (
        "arena-multi-agent-plus-serve-llms-staggered-retained-fifty-seat-run"
    )
    assert readiness["supersedes"] == (
        "evidence/september-17-multicluster-three-workshop-readiness-2026-09-07.json"
    )
    per_cluster = readiness["per_cluster_reservations"]
    assert per_cluster["arena"]["pod_slots"] == 100
    assert per_cluster["brutus"]["pod_slots"] == 75
    assert per_cluster["arena"]["protected_pod_slots"] == 120
    assert per_cluster["brutus"]["protected_pod_slots"] == 90
    excluded_oberon = readiness["excluded_targets"]["oberon"]
    assert excluded_oberon["execution_enabled"] is False
    assert excluded_oberon["observed_safe_max_serve_llms_seats"] == 19
    assert excluded_oberon["cleanup_result"] == "RED"

    activation = readiness["target_activation"]
    assert activation["arena"]["enabled"] is True
    assert activation["brutus"]["enabled"] is False
    assert all(target["event_override_required"] is True for target in activation.values())


def test_event_readiness_manifest_is_hash_verified():
    expected = READINESS_CHECKSUM.read_text().split()[0]
    assert hashlib.sha256(READINESS.read_bytes()).hexdigest() == expected


def test_multicluster_contract_evidence_is_hash_verified_and_does_not_overclaim():
    evidence = json.loads(CONTRACT_EVIDENCE.read_text())
    checksum = CONTRACT_EVIDENCE.with_suffix(".json.sha256")

    assert evidence["schema"] == ("launchpad.redhat.com/event-contract-test-evidence/v2")
    assert evidence["green"]["regression"]["passed"] == 1146
    assert evidence["live_boundary"]["live_capacity_preflight_run"] is False
    assert evidence["live_boundary"]["cluster_mutations"] == 0
    assert evidence["release_status"] == "RED"
    assert evidence["contains_plaintext_credentials"] is False
    expected = checksum.read_text().split()[0]
    assert hashlib.sha256(CONTRACT_EVIDENCE.read_bytes()).hexdigest() == expected


def test_event_runbook_names_every_gate_and_does_not_overclaim_capacity():
    runbook = RUNBOOK.read_text()

    for value in (
        "September 17, 2026",
        "multi-agent-quickstart",
        "intel-llm-cpu-serving",
        "intel-xeon6-agent-201",
        "57,000m",
        "111,200 MiB",
        "175",
        "two execution clusters",
        "Arena",
        "Oberon",
        "Brutus",
        "evidence/arena-staggered-three-workshops-2026-09-04.json",
        "evidence/brutus-agent-201-three-pod-certification-2026-09-05.json",
        "Exact-trio run 01 — RED",
        "Exact-trio run 02 — RED",
        "evidence/september-17-agentic-trio-run02-red-2026-09-06.json",
        "evidence/september-17-agentic-trio-run02-remediation-2026-09-06.json",
    ):
        assert value in runbook

    normalized_runbook = " ".join(runbook.lower().split())
    assert "public access is not certified" in normalized_runbook
    assert "aggregate arena capacity" in normalized_runbook
    assert "Multi-Agent first" in runbook
    assert "AgentOps remains available as a five-seat pilot" in runbook
    assert "zero residue" in runbook


def test_two_cluster_live_preflight_proves_capacity_without_overclaiming_release():
    evidence = json.loads(TWO_CLUSTER_PREFLIGHT.read_text())

    assert evidence["schema"] == ("launchpad.redhat.com/event-preflight-evidence/v1")
    assert evidence["mutates_cluster"] is False
    assert evidence["target_inspection"]["passed"] is True
    assert evidence["aggregate_capacity"]["passed"] is True
    assert evidence["aggregate_capacity"]["clusters"]["arena"]["required"]["pods"] == 120
    assert evidence["aggregate_capacity"]["clusters"]["arena"]["available"]["pods"] == 284
    assert [check["passed"] for check in evidence["checks"]] == [
        True,
        True,
        False,
    ]
    assert evidence["result"] == "RED"
    assert "disabled" in evidence["checks"][2]["placement_reason"]
    checksum = TWO_CLUSTER_PREFLIGHT.with_suffix(".json.sha256")
    expected = checksum.read_text().split()[0]
    assert hashlib.sha256(TWO_CLUSTER_PREFLIGHT.read_bytes()).hexdigest() == expected


def test_every_event_catalog_blocks_recently_recovered_workers():
    for catalog_item_id in (
        "multi-agent-quickstart",
        "intel-llm-cpu-serving",
        "intel-xeon6-agent-201",
    ):
        catalog = yaml.safe_load(
            (ROOT / "catalog" / catalog_item_id / "catalog-item.yaml").read_text()
        )
        assert catalog["metadata"]["workshop_node_spread"] is True
        assert catalog["metadata"]["workshop_node_min_ready_seconds"] == 900


def test_brutus_and_excluded_oberon_remain_fail_closed_until_their_gates_pass():
    rendered = yaml.safe_load(
        (ROOT / "deploy/launchpad/overlays/arena/arena-clusters.yaml").read_text()
    )
    targets = yaml.safe_load(rendered["data"]["clusters.yaml"])["clusters"]
    by_id = {target["cluster_id"]: target for target in targets}

    assert by_id["arena"].get("enabled", True) is True
    assert by_id["oberon"]["enabled"] is False
    assert by_id["brutus"]["enabled"] is False
