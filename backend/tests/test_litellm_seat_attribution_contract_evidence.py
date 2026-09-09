"""Contract for the bounded LiteLLM seat-attribution implementation evidence."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT / "evidence/runs/litellm-seat-attribution-contract-green-20260909.json"
)


def test_attribution_evidence_is_green_locally_without_overclaiming_live_data():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["result"] == "GREEN-local-contract-RED-live-data-path"
    assert evidence["contains_plaintext_credentials"] is False
    assert evidence["green"]["focused_backend"] == "12 passed"
    assert evidence["green"]["frontend_production_build"] == "passed"
    assert all(evidence["implemented_contract"].values())

    live = evidence["live_boundary"]
    assert live["litellm_proxy_deployed_on_arena"] is False
    assert live["authoritative_spend_events_available"] is False
    assert live["live_seat_attribution_certified"] is False
    assert live["cluster_mutations"] == 0

    matrix = {row["gate"]: row["state"] for row in evidence["red_green_matrix"]}
    assert matrix["stable virtual-key/session identity"] == "GREEN-local"
    assert matrix["version-pinned security-reviewed proxy"] == "RED-pending"
    assert matrix["25-seat authoritative live attribution"] == "RED-pending"


def test_attribution_evidence_checksum_is_immutable():
    checksum = Path(f"{EVIDENCE}.sha256")
    expected = checksum.read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
