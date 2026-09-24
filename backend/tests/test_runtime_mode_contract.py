"""Contracts for supported Launchpad runtime modes."""

from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_startup_and_service_factory_reject_retired_mode() -> None:
    from app.main import _validate_config

    with patch.dict("os.environ", {"LAUNCHPAD_MODE": "rhdp"}, clear=False):
        with pytest.raises(RuntimeError, match="Unsupported LAUNCHPAD_MODE=rhdp"):
            _validate_config()


def test_service_factory_has_no_legacy_runtime_imports() -> None:
    source = (ROOT / "backend/app/api/deps.py").read_text()

    assert 'mode == "rhdp"' not in source
    assert "app.adapters.rhdp" not in source
    assert "RHDPPoolAdapter" not in source


def test_current_runtime_modes_remain_supported() -> None:
    from app.main import SUPPORTED_LAUNCHPAD_MODES

    assert SUPPORTED_LAUNCHPAD_MODES == {"mock", "local", "openshift"}
