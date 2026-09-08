"""EDD contract for the Arena workshop-load resilience diagnosis."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/arena-resilience-analysis-2026-09-08.json"


def test_arena_resilience_analysis_preserves_the_functional_and_network_boundaries():
    receipt = json.loads(EVIDENCE.read_text())

    assert receipt["schema"] == "launchpad.redhat.com/arena-resilience-analysis/v1"
    assert receipt["cluster_ref"] == "arena"
    assert receipt["workload_result"] == {"passed": 75, "failed": 0}
    assert receipt["network_resilience_status"] == "RED-live"
    assert receipt["observations"]["probe_events"]["context_deadline_records"] > 0
    assert receipt["observations"]["nodes"]["rhgnr1"]["conntrack_ratio_max"] > 0.8
    assert receipt["observations"]["nodes"]["gnr2.fm2aihpcsed.com"]["cpu_busy_percent_max"] < 25
    assert receipt["observations"]["nodes"]["gnr2.fm2aihpcsed.com"]["kubelet_exec_sync_p99_seconds"] > 10
    assert receipt["conclusion"]["causality_proven"] is False
    assert receipt["pilot_controls"]["participant_wave_transport"] == "HTTPS routes"
    assert receipt["pilot_controls"]["deep_admin_concurrency"] == 5
    assert receipt["contains_plaintext_credentials"] is False


def test_arena_resilience_analysis_is_hashed_and_documents_the_recommended_path():
    raw = EVIDENCE.read_bytes()
    checksum = Path(f"{EVIDENCE}.sha256").read_text().split()[0]
    assert hashlib.sha256(raw).hexdigest() == checksum

    recommendation = (ROOT / "docs/arena-resilience-recommendation.md").read_text()
    for phrase in (
        "HTTPS participant wave",
        "kubelet/CRI",
        "conntrack",
        "Keep `rhgnr1` cordoned",
        "dynamic policy reload",
        "not production-certified",
    ):
        assert phrase in recommendation
