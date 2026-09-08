"""Contract for the read-only Arena resilience evidence collector."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/capture-arena-resilience.sh"


def test_arena_resilience_collector_is_explicit_and_read_only():
    source = SCRIPT.read_text()

    assert (
        'DEFAULT_KUBECONFIG="/Users/jkershaw/Documents/launchpad/.arena-kubeconfig"'
        in source
    )
    assert 'OC=(oc "--kubeconfig=${ARENA_KUBECONFIG}")' in source
    assert 'get --raw="/readyz"' in source
    assert 'get nodes -o json' in source
    assert 'get pods -A -o json' in source
    assert 'get events -A -o json' in source
    assert 'get kubeletconfig -o json' in source
    assert 'adm node-logs' in source

    forbidden = (
        " apply ",
        " create ",
        " delete ",
        " patch ",
        " replace ",
        " scale ",
        " cordon ",
        " uncordon ",
        " drain ",
    )
    for verb in forbidden:
        command = verb.strip()
        assert re.search(
            rf'\"\$\{{OC\[@\]\}}\"\s+{re.escape(command)}\b', source
        ) is None


def test_arena_resilience_collector_captures_required_pilot_signals():
    source = SCRIPT.read_text()

    for artifact in (
        "metadata.json",
        "api-latency.json",
        "nodes.json",
        "qos-density.json",
        "critical-pods.json",
        "probe-waves.json",
        "kubelet-config.json",
        "node-runtime-warnings.json",
        "manifest.sha256",
    ):
        assert artifact in source

    assert "openshift-ovn-kubernetes" in source
    assert "openshift-multus" in source
    assert "openshift-dns" in source
    assert "openshift-ingress" in source
    assert "context deadline exceeded" in source
    assert "i/o timeout" in source
    assert "PLEG is not healthy" in source
    assert "matching_lines" in source
    assert "lines: ." not in source
    assert "contains_plaintext_credentials" in source
    assert "max(0, (${after}-${before}))" in source
