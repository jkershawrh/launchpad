"""Source-only Flightpath execution preflight contract."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/flightpath_execution_preflight.py"


def _module():
    spec = importlib.util.spec_from_file_location("flightpath_execution_preflight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_copy(tmp_path: Path) -> Path:
    overlay = Path("deploy/launchpad/overlays/arena/arena-clusters.yaml")
    destination = tmp_path / overlay
    destination.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / overlay, destination)
    for catalog_id in _module().PILOT_CATALOG_IDS:
        relative = Path("catalog") / catalog_id / "catalog-item.yaml"
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path


def test_preflight_reports_static_green_without_claiming_runtime_proof() -> None:
    report = _module().evaluate()

    assert report["static_contract_passed"] is True
    assert report["mutates_cluster"] is False
    assert set(report["catalogs"]) == set(_module().PILOT_CATALOG_IDS)
    assert set(report["runtime_proof"].values()) == {"not_run"}


def test_preflight_fails_if_flightpath_image_drifts_to_internal_registry(tmp_path: Path) -> None:
    root = _source_copy(tmp_path)
    path = root / "deploy/launchpad/overlays/arena/arena-clusters.yaml"
    overlay = yaml.safe_load(path.read_text())
    targets = yaml.safe_load(overlay["data"]["clusters.yaml"])
    flightpath = next(item for item in targets["clusters"] if item["cluster_id"] == "flightpath")
    flightpath["image_references"]["showroom_terminal"] = (
        "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/terminal"
    )
    overlay["data"]["clusters.yaml"] = yaml.safe_dump(targets)
    path.write_text(yaml.safe_dump(overlay))

    report = _module().evaluate(root)

    assert report["static_contract_passed"] is False
    assert all(
        not item["checks"]["no_internal_registry_grant_needed"]
        for item in report["catalogs"].values()
    )


def test_preflight_fails_if_required_model_route_disappears(tmp_path: Path) -> None:
    root = _source_copy(tmp_path)
    path = root / "deploy/launchpad/overlays/arena/arena-clusters.yaml"
    overlay = yaml.safe_load(path.read_text())
    targets = yaml.safe_load(overlay["data"]["clusters.yaml"])
    flightpath = next(item for item in targets["clusters"] if item["cluster_id"] == "flightpath")
    flightpath["model_endpoints"] = {}
    overlay["data"]["clusters.yaml"] = yaml.safe_dump(targets)
    path.write_text(yaml.safe_dump(overlay))

    report = _module().evaluate(root)

    assert report["static_contract_passed"] is False
    assert any(
        not item["checks"]["model_routes_declared"]
        for item in report["catalogs"].values()
    )
