from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_convergence_candidate.py"
CANDIDATE = ROOT / "certification/candidates/staging-candidate-20260922.yaml"


def _module():
    spec = importlib.util.spec_from_file_location("convergence_candidate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate() -> dict:
    return yaml.safe_load(CANDIDATE.read_text(encoding="utf-8"))


def test_repository_candidate_binds_platform_catalogs_and_evidence() -> None:
    result = _module().validate(_candidate(), root=ROOT)
    assert result == {
        "valid": True,
        "candidate_id": "launchpad-staging-20260922-01",
        "stage": "green-integration",
        "platform_revision": "4f8d68b80e4d7cbb8edae96728536d2f9d44ca26",
        "catalog_count": 3,
        "evidence_count": 4,
        "next_stage": "green-canary",
    }


def test_catalog_or_evidence_drift_fails_closed() -> None:
    module = _module()
    candidate = _candidate()
    candidate["catalog_releases"][0]["version"] = "wrong"
    with pytest.raises(ValueError, match="catalog identity drift"):
        module.validate(candidate, root=ROOT)
    candidate = _candidate()
    candidate["catalog_releases"][0]["effective_release"]["version"] = "wrong"
    with pytest.raises(ValueError, match="effective catalog identity drift"):
        module.validate(candidate, root=ROOT)
    candidate = _candidate()
    candidate["evidence"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="evidence hash drift"):
        module.validate(candidate, root=ROOT)


def test_promotion_requires_named_approval_and_next_gate_blockers() -> None:
    module = _module()
    candidate = copy.deepcopy(_candidate())
    candidate["current_stage"] = "green-canary"
    candidate["approval"] = {"required": True, "approved_by": None, "approved_at": None}
    with pytest.raises(ValueError, match="named approval"):
        module.validate(candidate, root=ROOT)

    candidate["approval"] = {
        "required": True,
        "approved_by": "release-owner",
        "approved_at": "2026-09-23T03:00:00Z",
    }
    candidate["blockers_to_green_staging"] = []
    with pytest.raises(ValueError, match="blockers to green-staging"):
        module.validate(candidate, root=ROOT)
