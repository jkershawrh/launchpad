"""Contract for the revised September 17 agentic workshop release gate."""

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
READINESS = (
    ROOT / "evidence/september-17-agentic-three-workshop-readiness-2026-09-06.json"
)
RUNBOOK = ROOT / "docs/september-17-agentic-three-workshop-readiness.md"
READINESS_CHECKSUM = READINESS.with_suffix(".json.sha256")


def test_event_readiness_manifest_keeps_the_exact_workshop_target_and_budget():
    readiness = json.loads(READINESS.read_text())

    assert readiness["schema"] == "launchpad.redhat.com/event-readiness/v2"
    assert readiness["event_date"] == "2026-09-17"
    assert readiness["deployment_scope"] == "fleet"
    assert readiness["candidate_cluster_targets"] == {
        "multi-agent-quickstart": "arena",
        "intel-llm-cpu-serving": "arena",
        "intel-xeon6-agent-201": "arena",
    }
    assert readiness["provisioning_mode"] == "staggered"
    assert readiness["concurrent_participant_seats"] == 75

    workshops = readiness["workshops"]
    assert [workshop["catalog_item_id"] for workshop in workshops] == [
        "multi-agent-quickstart",
        "intel-llm-cpu-serving",
        "intel-xeon6-agent-201",
    ]
    assert all(workshop["seat_count"] == 25 for workshop in workshops)
    assert workshops[0]["release_status"] == "GREEN-live-25-x3-internal"
    assert workshops[1]["release_status"] == "GREEN-live-25"
    assert workshops[2]["release_status"] == "GREEN-live-25-prior-arena-release"

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

    assert readiness["previous_pattern_evidence"] == (
        "evidence/arena-staggered-three-workshops-2026-09-04.json"
    )
    assert readiness["public_access_certified"] is False
    assert readiness["overall_status"] == "RED"
    assert readiness["next_gate"] == (
        "deploy-run02-remediation-then-exact-agentic-trio-run03"
    )
    assert readiness["supersedes"] == (
        "evidence/september-17-three-workshop-readiness-2026-09-05.json"
    )
    assert readiness["substitution"]["removed_catalog_item_id"] == (
        "agentops-observability"
    )
    assert readiness["substitution"]["replacement_catalog_item_id"] == (
        "multi-agent-quickstart"
    )
    assert readiness["latest_multi_agent_promotion_evidence"] == (
        "evidence/multi-agent-quickstart-25-seat-promotion-2026-09-06.json"
    )
    assert readiness["latest_exact_trio_evidence"] == (
        "evidence/september-17-agentic-trio-run02-red-2026-09-06.json"
    )
    assert readiness["capacity_status"]["active_worker_pods"] == 216
    assert readiness["capacity_status"]["available_slots_after_reserve"] == 184
    assert readiness["capacity_status"]["remaining_slots_after_event"] == 9
    assert readiness["capacity_status"]["fit_decision"] == (
        "fits-current-snapshot-with-narrow-pod-margin"
    )


def test_event_readiness_manifest_is_hash_verified():
    expected = READINESS_CHECKSUM.read_text().split()[0]
    assert hashlib.sha256(READINESS.read_bytes()).hexdigest() == expected


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
        "184",
        "evidence/arena-staggered-three-workshops-2026-09-04.json",
        "Exact-trio run 01 — RED",
        "Exact-trio run 02 — RED",
        "evidence/september-17-agentic-trio-run02-red-2026-09-06.json",
        "evidence/september-17-agentic-trio-run02-remediation-2026-09-06.json",
    ):
        assert value in runbook

    normalized_runbook = " ".join(runbook.lower().split())
    assert "public access is not certified" in normalized_runbook
    assert "current free arena capacity must be measured live" in normalized_runbook
    assert "Multi-Agent first" in runbook
    assert "AgentOps remains available as a five-seat pilot" in runbook
    assert "zero residue" in runbook


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
