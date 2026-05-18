#!/usr/bin/env python3
"""Tests for Overdrive routing matrix — TDD RED phase."""

import pytest
import sys
from pathlib import Path


@pytest.fixture
def matrix_module(project_root):
    gw = str(project_root / "gateway")
    sys.path.insert(0, gw)
    try:
        import importlib
        import overdrive.matrix as matrix
        importlib.reload(matrix)
        yield matrix
    finally:
        sys.path.remove(gw)


@pytest.fixture
def config_path(project_root):
    return project_root / "gateway" / "overdrive" / "config.yaml"


class TestMatrixLoader:
    def test_config_file_exists(self, config_path):
        assert config_path.exists(), "gateway/overdrive/config.yaml missing"

    def test_config_loads(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        assert isinstance(config, dict)
        assert "lanes" in config
        assert "routing_matrix" in config
        assert "fallback_rules" in config

    def test_config_has_three_lanes(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        assert set(config["lanes"].keys()) == {"eco", "performance", "overdrive"}

    def test_lanes_have_required_fields(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        for lane_name, lane in config["lanes"].items():
            assert "target_endpoint" in lane, f"{lane_name} missing target_endpoint"
            assert "capabilities" in lane, f"{lane_name} missing capabilities"
            assert "max_token_estimate" in lane, f"{lane_name} missing max_token_estimate"

    def test_routing_matrix_has_entries(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        assert len(config["routing_matrix"]) >= 7

    def test_invalid_config_raises(self, matrix_module, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("not_valid: true")
        with pytest.raises(ValueError):
            matrix_module.load_config(bad)


class TestMatrixMatching:
    def test_classification_to_eco(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        lane = matrix_module.match_lane("classification", 1000, "normal", 8000, config)
        assert lane == "eco"

    def test_embedding_to_performance(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        lane = matrix_module.match_lane("embedding", 6000, "normal", 5000, config)
        assert lane == "performance"

    def test_rerank_to_performance(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        lane = matrix_module.match_lane("rerank", 6000, "normal", 5000, config)
        assert lane == "performance"

    def test_short_summary_to_performance(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        lane = matrix_module.match_lane("short_summary", 8000, "normal", 8000, config)
        assert lane == "performance"

    def test_long_summary_to_overdrive(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        lane = matrix_module.match_lane("long_summary", 24000, "high", 5000, config)
        assert lane == "overdrive"

    def test_incident_rca_to_overdrive(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        lane = matrix_module.match_lane("incident_rca", 32000, "critical", 5000, config)
        assert lane == "overdrive"

    def test_batch_summary_to_overdrive(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        lane = matrix_module.match_lane("batch_summary", 40000, "high", 10000, config)
        assert lane == "overdrive"


class TestUnknownTask:
    def test_unknown_returns_none(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        lane = matrix_module.match_lane("unknown", 1000, "normal", 5000, config)
        assert lane is None


class TestFallback:
    def test_overdrive_fallback_to_performance(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        fb = matrix_module.get_fallback("overdrive", "long_summary", 24000, config)
        assert fb == "performance"

    def test_overdrive_no_fallback_large_batch(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        fb = matrix_module.get_fallback("overdrive", "batch_summary", 40000, config)
        assert fb is None

    def test_performance_fallback_to_eco_classification(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        fb = matrix_module.get_fallback("performance", "classification", 1000, config)
        assert fb == "eco"

    def test_performance_no_fallback_embedding(self, matrix_module, config_path):
        config = matrix_module.load_config(config_path)
        fb = matrix_module.get_fallback("performance", "embedding", 6000, config)
        assert fb is None
