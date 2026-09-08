"""Contract for the exact Sep 17 three-workshop concurrent live proof."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/september-17-exact-75-live-2026-09-08.json"
CHECKSUM = Path(f"{EVIDENCE}.sha256")


def test_exact_75_live_receipt_proves_the_internal_pilot_boundary():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["schema"] == (
        "launchpad.redhat.com/september-17-exact-75-live/v1"
    )
    assert evidence["release_status"] == "GREEN-live-internal-pilot-candidate"
    assert evidence["production_status"] == "RED-not-production-certified"
    assert evidence["provisioning_mode"] == "staggered-retained"
    assert evidence["concurrent_participant_seats"] == 75

    expected = {
        "building-an-ai-agent": (
            "36a501d8-4754-4632-bf33-67cf6d4c4649",
            "intel-xeon6-agent-201",
            "brutus",
        ),
        "multi-agent": (
            "e85a59c5-66a7-4b25-a0dc-66a74eafd372",
            "multi-agent-quickstart",
            "arena",
        ),
        "serve-llms": (
            "04126518-64b5-43d3-aa95-5b61934fc019",
            "intel-llm-cpu-serving",
            "arena",
        ),
    }
    observed = {
        name: (
            workshop["workshop_id"],
            workshop["catalog_item_id"],
            workshop["cluster_ref"],
        )
        for name, workshop in evidence["workshops"].items()
    }
    assert observed.keys() == expected.keys()
    for workshop_name, expected_identity in expected.items():
        assert observed[workshop_name] == expected_identity
    assert all(
        workshop["seat_count"] == 25
        and workshop["ready_seats"] == 25
        and workshop["functional"]["passed"] == 25
        and workshop["functional"]["failed"] == 0
        for workshop in evidence["workshops"].values()
    )

    proof = evidence["concurrent_live_proof"]
    assert proof["started_together_within_seconds"] <= 10
    assert proof["participants_started"] == 75
    assert proof["participants_passed"] == 75
    assert proof["participants_failed"] == 0
    assert proof["cross_namespace_denials"] == 50
    assert proof["node_list_denials"] == 50
    assert proof["contains_plaintext_credentials"] is False

    post = evidence["post_run_state"]
    assert post["arena_api_ready"] is True
    assert post["rhgnr1_cordoned"] is True
    assert post["multi_agent_containers"] == {"ready": 275, "total": 275}
    assert post["serve_llms_containers"] == {"ready": 100, "total": 100}
    assert post["vllm"] == {"ready_replicas": 2, "replicas": 2, "restarts": 0}
    assert post["workflow_policy_configmaps"] == 0
    assert post["arena_certification_pods"] == 0
    assert post["brutus_certification_pods"] == 0

    boundaries = evidence["open_gates"]
    assert boundaries["public_access_25_seat_browser_run"] == "RED-pending"
    assert boundaries["exact_trio_reclaim_zero_residue"] == "RED-pending-retained"
    assert boundaries["arena_network_resilience"] == "RED-live-observed-stall"
    assert evidence["rubric"]["score"] < evidence["rubric"]["required"]


def test_exact_75_live_receipt_is_hashed_red_green_and_secret_safe():
    raw = EVIDENCE.read_bytes()
    expected_hash = CHECKSUM.read_text().split()[0]

    assert hashlib.sha256(raw).hexdigest() == expected_hash
    evidence = json.loads(raw)
    states = {row["state"] for row in evidence["red_green_matrix"]}
    assert any(state.startswith("RED") for state in states)
    assert any(state.startswith("GREEN") for state in states)

    text = raw.decode()
    for forbidden in (
        "kubeadmin",
        "BEGIN " + "PRIVATE" + " KEY",
        "MAAS_API_KEY\"",
        "MODEL_API_KEY\"",
        "AGENT_AUTH_TOKEN\"",
        "sk-launchpad-",
    ):
        assert forbidden not in text
