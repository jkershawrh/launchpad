#!/usr/bin/env python3
"""Stage 1: Power Modes — TDD Red Phase"""

import sys
import pytest
from pathlib import Path


@pytest.fixture
def overdrive_dir(project_root):
    d = project_root / "gateway" / "overdrive"
    if str(d.parent) not in sys.path:
        sys.path.insert(0, str(d.parent))
    return d


class TestPowerModeDefinitions:

    def test_module_importable(self, overdrive_dir):
        from overdrive.power_modes import POWER_MODES
        assert isinstance(POWER_MODES, dict)

    def test_all_modes_exist(self, overdrive_dir):
        from overdrive.power_modes import POWER_MODES
        expected = {"standby", "drive", "boost", "overdrive", "max_q", "cooldown"}
        assert set(POWER_MODES.keys()) == expected

    def test_standby_count(self, overdrive_dir):
        from overdrive.power_modes import POWER_MODES
        assert POWER_MODES["standby"]["count"] == 5

    def test_drive_count(self, overdrive_dir):
        from overdrive.power_modes import POWER_MODES
        assert POWER_MODES["drive"]["count"] == 25

    def test_boost_count(self, overdrive_dir):
        from overdrive.power_modes import POWER_MODES
        assert POWER_MODES["boost"]["count"] == 250

    def test_overdrive_count(self, overdrive_dir):
        from overdrive.power_modes import POWER_MODES
        assert POWER_MODES["overdrive"]["count"] == 1000

    def test_cooldown_count(self, overdrive_dir):
        from overdrive.power_modes import POWER_MODES
        assert POWER_MODES["cooldown"]["count"] == 5

    def test_max_q_accepts_custom(self, overdrive_dir):
        from overdrive.power_modes import get_mode_config
        cfg = get_mode_config("max_q", count=5000, concurrency=100)
        assert cfg["count"] == 5000
        assert cfg["concurrency"] == 100

    def test_each_mode_has_concurrency(self, overdrive_dir):
        from overdrive.power_modes import POWER_MODES
        for name, mode in POWER_MODES.items():
            assert "concurrency" in mode, f"{name} missing concurrency"
            assert isinstance(mode["concurrency"], int)
            assert mode["concurrency"] > 0

    def test_get_mode_config_returns_copy(self, overdrive_dir):
        from overdrive.power_modes import get_mode_config
        a = get_mode_config("drive")
        b = get_mode_config("drive")
        assert a == b
        a["count"] = 999
        assert b["count"] == 25

    def test_get_mode_config_invalid_mode(self, overdrive_dir):
        from overdrive.power_modes import get_mode_config
        with pytest.raises(ValueError):
            get_mode_config("turbo")

    def test_list_modes(self, overdrive_dir):
        from overdrive.power_modes import list_modes
        modes = list_modes()
        assert len(modes) == 6
        assert all(isinstance(m, dict) for m in modes)
        assert all("name" in m and "count" in m for m in modes)
