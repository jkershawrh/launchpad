from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/validate_flightpath_promotion_bundle.py"
BUNDLE = ROOT / "certification/releases/flightpath-candidate-03/bundle.yaml"
BUNDLE_04 = ROOT / "certification/releases/flightpath-candidate-04/bundle.yaml"


def _module():
    spec = importlib.util.spec_from_file_location("flightpath_bundle", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle() -> dict:
    return yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))


def _bundle_04() -> dict:
    return yaml.safe_load(BUNDLE_04.read_text(encoding="utf-8"))


def test_bundle_binds_promotion_and_rollback_identities() -> None:
    result = _module().validate(_bundle(), root=ROOT)
    assert result["valid"] is True
    assert result["identities"]["promotion"]["candidate_id"] == "launchpad-staging-20260923-03"
    assert result["identities"]["rollback"]["candidate_id"] == "launchpad-staging-20260922-02"


def test_public_canary_bundle_binds_all_signed_platform_images() -> None:
    bundle = _bundle_04()
    result = _module().validate(bundle, root=ROOT)
    assert result["valid"] is True
    assert result["bundle_id"] == "flightpath-candidate-04"
    assert bundle["target"]["public_max_seats"] == 1
    assert len(bundle["canary"]["catalog_ids"]) == 6
    assert bundle["canary"]["public_catalog_ids"] == ["network-operations-agent"]
    assert result["identities"]["rollback"]["candidate_id"] == (
        "launchpad-staging-20260925-04-compatible-rollback"
    )


def test_public_canary_bundle_fails_closed_on_scope_or_image_drift() -> None:
    module = _module()
    bundle = copy.deepcopy(_bundle_04())
    bundle["target"]["public_max_seats"] = 2
    with pytest.raises(ValueError, match="one seat"):
        module.validate(bundle, root=ROOT)

    bundle = copy.deepcopy(_bundle_04())
    bundle["promotion"]["requester_image"] = bundle["promotion"]["admin_image"]
    with pytest.raises(ValueError, match="requester_image does not match"):
        module.validate(bundle, root=ROOT)

    bundle = copy.deepcopy(_bundle_04())
    bundle["rollback"]["admin_image"] = bundle["rollback"]["requester_image"]
    with pytest.raises(ValueError, match="rollback admin_image does not match"):
        module.validate(bundle, root=ROOT)

    bundle = copy.deepcopy(_bundle_04())
    bundle["canary"]["public_catalog_ids"].append("agent-reliability")
    with pytest.raises(ValueError, match="public canary scope"):
        module.validate(bundle, root=ROOT)

    bundle = copy.deepcopy(_bundle_04())
    bundle["canary"]["max_concurrent_canaries"] = 2
    with pytest.raises(ValueError, match="sequentially"):
        module.validate(bundle, root=ROOT)

    bundle = copy.deepcopy(_bundle_04())
    bundle["gates"]["candidate_routes_reachable"] = False
    with pytest.raises(ValueError, match="candidate_routes_reachable"):
        module.validate(bundle, root=ROOT)


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
