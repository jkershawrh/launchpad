"""Contracts for the repeatable September 17 retained-topology soak."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts/soak-september-17-exact-75.sh"


def test_exact_75_soak_is_bounded_fail_closed_and_credential_free():
    source = DRIVER.read_text()

    assert ': "${KUBECONFIG:?' in source
    assert "api.arena.fm2aihpcsed.com" in source
    assert "SOAK_DURATION_SECONDS:-3600" in source
    assert "SOAK_INTERVAL_SECONDS:-60" in source
    assert "launchpad.redhat.com/workshop-id" in source
    assert "showroom_http_200" in source
    assert "arena_unready_pods" in source
    assert "arena_restart_total" in source
    assert "granite_tools_http" in source
    assert "nomic_embed_http" in source
    assert "contains_plaintext_credentials: false" in source
    assert "snapshots.jsonl" in source
    assert "summary.json.sha256" in source
    assert '"requested_duration_seconds"' in source
    assert 'result="GREEN-live-soak"' in source
    assert 'result="RED-live-soak"' in source
    assert 'result="GREEN-live-sixty-minute-soak"' not in source
    assert "oc config use-context" not in source
