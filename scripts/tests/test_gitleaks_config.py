from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".gitleaks.toml"


def test_gitleaks_allowlist_does_not_exempt_generic_sha256_lines() -> None:
    """A digest on a line must not hide a credential on that same line."""
    payload = tomllib.loads(CONFIG.read_text())
    allowlist = payload.get("allowlist") or {}
    regexes = allowlist.get("regexes") or []
    digest = "a" * 64

    assert allowlist.get("regexTarget") == "line"
    assert not any(re.search(pattern, digest) for pattern in regexes)


def test_gitleaks_extends_maintained_default_rules() -> None:
    payload = tomllib.loads(CONFIG.read_text())

    assert (payload.get("extend") or {}).get("useDefault") is True
