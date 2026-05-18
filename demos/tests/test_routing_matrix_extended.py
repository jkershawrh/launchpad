#!/usr/bin/env python3
"""Stage 4: Extended Routing Matrix — TDD Red Phase

Tests new task types (rag_question, document_summary, code_summary)
AND regression for existing 7 routing rules.
"""

import sys
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def add_gateway_to_path(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def config(project_root):
    from overdrive.matrix import load_config
    return load_config(project_root / "gateway" / "overdrive" / "config.yaml")


class TestExistingRoutesRegression:
    """Ensure existing 7 rules still work after extending the matrix."""

    def test_classification_to_eco(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("classification", 1000, "normal", 8000, config) == "eco"

    def test_embedding_to_performance(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("embedding", 4000, "normal", 5000, config) == "performance"

    def test_rerank_to_performance(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("rerank", 4000, "normal", 5000, config) == "performance"

    def test_short_summary_to_performance(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("short_summary", 8000, "normal", 8000, config) == "performance"

    def test_long_summary_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("long_summary", 20000, "high", 5000, config) == "overdrive"

    def test_incident_rca_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("incident_rca", 25000, "critical", 5000, config) == "overdrive"

    def test_batch_summary_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("batch_summary", 40000, "critical", 10000, config) == "overdrive"


class TestNewTaskTypes:
    """Test the 3 new task types added to the routing matrix."""

    def test_document_summary_routes_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        result = match_lane("document_summary", 20000, "high", 5000, config)
        assert result == "overdrive"

    def test_code_summary_routes_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        result = match_lane("code_summary", 18000, "high", 5000, config)
        assert result == "overdrive"

    def test_rag_question_small_to_performance(self, config):
        from overdrive.matrix import match_lane
        result = match_lane("rag_question", 4000, "normal", 5000, config)
        assert result == "performance"

    def test_rag_question_large_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        result = match_lane("rag_question", 20000, "high", 5000, config)
        assert result == "overdrive"

    def test_document_summary_in_overdrive_capabilities(self, config):
        caps = config["lanes"]["overdrive"]["capabilities"]
        assert "document_summary" in caps

    def test_code_summary_in_overdrive_capabilities(self, config):
        caps = config["lanes"]["overdrive"]["capabilities"]
        assert "code_summary" in caps

    def test_rag_question_in_performance_capabilities(self, config):
        caps = config["lanes"]["performance"]["capabilities"]
        assert "rag_question" in caps
