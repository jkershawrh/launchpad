"""Contract for the Serve LLMs v1.0.3 live Showroom acceptance."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/runs/intel-llm-cpu-serving-v103-live-20260909.json"


def test_v103_live_evidence_proves_rendered_content_function_and_cleanup():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["result"] == "GREEN-live"
    assert evidence["contains_plaintext_credentials"] is False
    assert evidence["repository"]["content_tag"] == (
        "pilot-2026-09-17-intel-llm-cpu-serving-v1.0.3"
    )
    assert evidence["deployment"]["backend_image_digest"].startswith("sha256:")
    assert evidence["deployment"]["workload_restart_count"] == 0
    assert evidence["catalog"]["version"] == "1.0.3"

    seat = evidence["acceptance_seat"]
    assert seat["cluster_ref"] == "arena"
    assert seat["exposure_policy"] == "internal"
    assert seat["provisioning_validation"] == {
        "showroom_pod_ready": True,
        "showroom_route_http_status": 200,
    }

    assert evidence["showroom"]["root_http_status"] == 200
    assert all(evidence["showroom"]["rendered_contract"].values())
    participant = evidence["participant_function"]
    assert participant["external_rag_route_http_status"] == 200
    assert participant["grounded_response"] is True
    assert participant["grounding_document"] == "orion-leave-policy.txt"
    assert participant["expected_fact_observed"] == "17"

    cleanup = evidence["cleanup"]
    assert cleanup["session_status"] == "reclaimed"
    assert cleanup["namespace_remaining"] is False
    for field in (
        "routes_remaining",
        "rolebindings_remaining",
        "argocd_applications_remaining",
    ):
        assert cleanup[field] == 0


def test_v103_live_evidence_checksum_is_immutable():
    checksum = Path(f"{EVIDENCE}.sha256")
    expected = checksum.read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
