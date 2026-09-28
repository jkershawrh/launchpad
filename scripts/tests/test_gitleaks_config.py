from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and earlier
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".gitleaks.toml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_gitleaks_allowlist_does_not_exempt_generic_sha256_lines() -> None:
    """A digest on a line must not hide a credential on that same line."""
    payload = tomllib.loads(CONFIG.read_text())
    allowlist = payload.get("allowlist") or {}
    regexes = allowlist.get("regexes") or []
    digest = "a" * 64

    assert not any(re.search(pattern, digest) for pattern in regexes)


def test_gitleaks_extends_maintained_default_rules() -> None:
    payload = tomllib.loads(CONFIG.read_text())

    assert (payload.get("extend") or {}).get("useDefault") is True


def test_global_allowlist_contains_no_content_regexes() -> None:
    """Content words must never suppress a secret on the same line."""
    payload = tomllib.loads(CONFIG.read_text())
    allowlist = payload.get("allowlist") or {}

    assert allowlist.get("regexes", []) == []


def test_ci_uses_checksum_verified_gitleaks_and_scans_event_range() -> None:
    workflow = CI_WORKFLOW.read_text()

    assert "gitleaks/gitleaks-action" not in workflow
    assert 'version="8.21.2"' in workflow
    assert "5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba" in workflow
    assert "sha256sum --check --strict" in workflow
    assert 'log_range="${BASE_SHA}..${HEAD_SHA}"' in workflow
    assert 'log_range="${BEFORE_SHA}..${HEAD_SHA}"' in workflow
    assert '--log-opts="$log_range"' in workflow
