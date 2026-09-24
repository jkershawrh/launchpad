from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/validate_flightpath_promotion_bundle.py"
BUNDLE = ROOT / "certification/releases/flightpath-candidate-03/bundle.yaml"


def _module():
    spec = importlib.util.spec_from_file_location("flightpath_bundle", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle() -> dict:
    return yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))


def test_bundle_binds_promotion_and_rollback_identities() -> None:
    result = _module().validate(_bundle(), root=ROOT)
    assert result["valid"] is True
    assert result["identities"]["promotion"]["candidate_id"] == "launchpad-staging-20260923-03"
    assert result["identities"]["rollback"]["candidate_id"] == "launchpad-staging-20260922-02"


@pytest.mark.parametrize("action", ["promotion", "rollback"])
def test_pinned_overlay_renders_to_declared_hash(action: str) -> None:
    module = _module()
    bundle = _bundle()
    payload = module.render(bundle, action, root=ROOT)
    assert payload.startswith(b"apiVersion:")


def test_bundle_fails_closed_on_identity_or_gate_drift() -> None:
    module = _module()
    bundle = copy.deepcopy(_bundle())
    bundle["promotion"]["revision"] = "0" * 40
    with pytest.raises(ValueError, match="does not resolve"):
        module.validate(bundle, root=ROOT)

    bundle = copy.deepcopy(_bundle())
    bundle["gates"]["dry_run_required"] = False
    with pytest.raises(ValueError, match="dry_run_required"):
        module.validate(bundle, root=ROOT)


def test_database_rollback_cannot_be_implicitly_authorized() -> None:
    module = _module()
    bundle = copy.deepcopy(_bundle())
    bundle["rollback"]["database_restore"] = "allowed"
    with pytest.raises(ValueError, match="database restore"):
        module.validate(bundle, root=ROOT)


def test_render_rejects_a_different_kustomize_version() -> None:
    module = _module()
    bundle = copy.deepcopy(_bundle())
    bundle["render"]["kustomize_version"] = "v0.0.0"
    with pytest.raises(ValueError, match="kustomize version"):
        module.render(bundle, "promotion", root=ROOT)
