"""Contract for the Arena attribution-contract deployment evidence."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT / "evidence/runs/litellm-seat-attribution-deployment-20260909.json"
)


def test_attribution_contract_is_deployed_without_overclaiming_live_usage():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["result"] == "GREEN-live-backward-compatible-contract"
    assert evidence["contains_plaintext_credentials"] is False
    assert evidence["target_cluster"] == "arena"
    assert all(
        build["result"] == "Complete"
        and build["source_commit"] == evidence["source_commit"]
        and build["digest"].startswith("sha256:")
        for build in evidence["builds"].values()
    )
    assert evidence["rollout"]["active_managed_lab_namespaces_during_rollout"] == 0
    assert evidence["rollout"]["rhgnr1_final_state"] == "Ready and cordoned"

    live = evidence["live_contract"]
    assert live["health"] == "ok"
    assert live["readiness"] == "ready"
    assert live["schema"] == "launchpad.admin-observability/v1"
    assert live["token_measurement"] == "unavailable"
    assert live["portal_http_status"] == 200
    assert live["portal_contains_token_formula"] is True

    boundary = evidence["live_boundary"]
    assert boundary["litellm_proxy_deployed_on_arena"] is False
    assert boundary["authoritative_spend_events_available"] is False
    assert boundary["one_seat_live_attribution_certified"] is False
    assert boundary["twenty_five_seat_live_attribution_certified"] is False


def test_attribution_contract_deployment_evidence_checksum_is_immutable():
    checksum = Path(f"{EVIDENCE}.sha256")
    expected = checksum.read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
