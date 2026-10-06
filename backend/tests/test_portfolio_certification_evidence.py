from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "evidence/lab-experience-review-20260930.yaml"

# One immutable, successful participant-journey receipt for every distinct
# orderable learning experience. Compatibility aliases and the platform smoke
# item are deliberately excluded because they are not additional labs.
CURRENT_ONE_SEAT_EVIDENCE = {
    "agentic-ai-101": "evidence/runs/catalog/agentic-ai-101-flightpath-full-participant-one-seat-20261005.json",
    "sovereign-ai-101": "evidence/runs/catalog/sovereign-ai-101-flightpath-console-operator-one-seat-20261005.json",
    "sovereign-ai-201": "evidence/runs/flightpath-live-20260930-sovereign-ai-201-1seat-r14.json",
    "virtualization-ai-foundations-101": "evidence/runs/flightpath-live-20261001-virtualization-ai-101-1seat-r10.json",
    "virtualization-ai-201": "evidence/runs/flightpath-live-20261001-virtualization-ai-201-1seat-r24.json",
    "virtualization-ai-301": "evidence/runs/flightpath-live-20261001-virtualization-ai-301-1seat-r15.json",
    "agent-reliability": "evidence/runs/flightpath-live-20261001-agent-reliability-1seat-r3.json",
    "intel-xeon6-agent-201": "evidence/runs/catalog/intel-xeon6-agent-201-flightpath-full-journey-one-seat-20261005-r3.json",
    "multi-agent-quickstart": "evidence/runs/catalog/multi-agent-quickstart-flightpath-full-journey-one-seat-20261005.json",
    "network-operations-agent": "evidence/runs/flightpath-live-20260930-network-operations-agent-1seat-r2.json",
    "hybrid-fraud-detection": "evidence/runs/catalog/hybrid-fraud-detection-flightpath-public-one-seat-20261002-r1.json",
    "intel-llm-cpu-serving": "evidence/runs/flightpath-live-20260930-intel-llm-cpu-serving-1seat-r2.json",
    "intel-llm-tool-calling": "evidence/runs/flightpath-live-20260930-intel-llm-tool-calling-1seat-r2.json",
    "ai-sandbox": "evidence/runs/flightpath-live-20261001-ai-sandbox-1seat-r6.json",
    "openshift-operators-workshop": "evidence/runs/flightpath-live-20261001-openshift-operators-workshop-1seat-r1.json",
    "operate-agentic-blueprint": "evidence/runs/catalog/operate-agentic-blueprint-flightpath-public-console-one-seat-20261005.json",
    "scale-agentic-blueprint": "evidence/runs/catalog/scale-agentic-blueprint-flightpath-qualification-operator-one-seat-20261005.json",
    "agentic-ai-601": "evidence/runs/catalog/agentic-ai-601-flightpath-qualification-operator-one-seat-20261005.json",
    "sovereign-ai-301": "evidence/runs/flightpath-live-20260930-sovereign-ai-301-1seat-r9.json",
    "sovereign-ai-401": "evidence/runs/flightpath-live-20260930-sovereign-ai-401-1seat-r15.json",
    "sovereign-ai-501": "evidence/runs/flightpath-live-20260930-sovereign-ai-501-1seat-r2.json",
    "virtualization-ai-401": "evidence/runs/flightpath-live-20260930-virtualization-ai-401-1seat-r9.json",
    "virtualization-ai-501": "evidence/runs/flightpath-live-20260930-virtualization-ai-501-1seat-r8.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_every_distinct_participant_lab_has_hashed_green_one_seat_evidence() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    participant_ids = set(review["labs"]) - {
        "cpu-inference-serving",
        "rag-on-xeon",
        "smoke-test",
    }

    assert set(CURRENT_ONE_SEAT_EVIDENCE) == participant_ids
    assert len(CURRENT_ONE_SEAT_EVIDENCE) == 23

    for catalog_id, relative_path in CURRENT_ONE_SEAT_EVIDENCE.items():
        evidence_path = ROOT / relative_path
        checksum_path = evidence_path.with_suffix(evidence_path.suffix + ".sha256")
        assert evidence_path.is_file(), catalog_id
        assert checksum_path.is_file(), catalog_id
        assert checksum_path.read_text(encoding="utf-8").split()[0] == _sha256(
            evidence_path
        ), catalog_id

        receipt = json.loads(evidence_path.read_text(encoding="utf-8"))
        result = (
            receipt.get("result")
            or receipt.get("status")
            or (receipt.get("promotion") or {}).get("result")
        )
        assert isinstance(result, str) and result.startswith("GREEN"), (
            catalog_id,
            result,
        )

        lab = review["labs"][catalog_id]
        assert "certified" in lab["overall_status"] or lab["overall_status"] in {
            "green-live-active-one-seat-certified",
            "one-seat-rehearsal-active",
        }, catalog_id
        assert lab["cleanup"]["status"].startswith("green-live"), catalog_id
