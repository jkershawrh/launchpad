from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy" / "launchpad" / "overlays" / "arena-convergence-canary"


def _render() -> list[dict]:
    result = subprocess.run(
        ["oc", "kustomize", str(OVERLAY)],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [item for item in yaml.safe_load_all(result.stdout) if item]


def _one(items: list[dict], kind: str, name: str) -> dict:
    matches = [
        item
        for item in items
        if item.get("kind") == kind and item.get("metadata", {}).get("name") == name
    ]
    assert len(matches) == 1
    return matches[0]


def test_canary_overlay_uses_durable_two_replica_backend() -> None:
    items = _render()
    backend = _one(items, "Deployment", "backend")
    assert backend["spec"]["replicas"] == 2
    assert backend["spec"]["strategy"] == {
        "type": "RollingUpdate",
        "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
    }
    assert backend["metadata"]["annotations"]["launchpad.redhat.com/ha-contract"] == (
        "postgres-leased-lifecycle-and-durable-public-access"
    )
    assert backend["spec"]["template"]["spec"]["topologySpreadConstraints"][0][
        "topologyKey"
    ] == "kubernetes.io/hostname"
    assert _one(items, "PodDisruptionBudget", "backend")["spec"]["minAvailable"] == 1


def test_canary_overlay_binds_effective_flightpath_catalogs() -> None:
    items = _render()
    backend = _one(items, "Deployment", "backend")
    worker = _one(items, "Deployment", "lifecycle-worker")
    expected = {
        "intel-llm-cpu-serving": "1.0.12-flightpath.1",
        "intel-xeon6-agent-201": "1.0.8-flightpath.1",
        "multi-agent-quickstart": "0.2.15-flightpath.1",
    }
    for catalog_id, version in expected.items():
        source = (
            ROOT
            / "deploy"
            / "launchpad"
            / "overlays"
            / "flightpath-candidate"
            / f"{catalog_id}.catalog-item.yaml"
        )
        catalog = yaml.safe_load(source.read_text(encoding="utf-8"))
        assert catalog["catalog_item_id"] == catalog_id
        assert str(catalog["version"]) == version
        path = f"/opt/catalog/{catalog_id}/catalog-item.yaml"
        assert any(mount.get("mountPath") == path for mount in backend["spec"]["template"]["spec"]["containers"][0]["volumeMounts"])
        assert any(mount.get("mountPath") == path for mount in worker["spec"]["template"]["spec"]["containers"][0]["volumeMounts"])

    apply_script = (OVERLAY / "apply.sh").read_text(encoding="utf-8")
    assert 'candidate="launchpad-staging-20260922-01"' in apply_script
    assert '"--confirm-candidate=$candidate"' in apply_script
    assert "api.arena.fm2aihpcsed.com" in apply_script
    for catalog_id in expected:
        assert f"{catalog_id}.catalog-item.yaml" in apply_script
        assert f"convergence-{catalog_id}-catalog" in apply_script


def test_canary_overlay_enables_leased_lifecycle_without_enabling_automation() -> None:
    items = _render()
    config = _one(items, "ConfigMap", "launchpad-config")["data"]
    assert config["LIFECYCLE_HA_ENABLED"] == "true"
    assert config["LIFECYCLE_JOB_LEASE_SECONDS"] == "120"
    assert config["ORPHAN_CLEANUP_ENABLED"] == "false"
    assert _one(items, "CronJob", "lifecycle-scheduler")["spec"]["suspend"] is True
