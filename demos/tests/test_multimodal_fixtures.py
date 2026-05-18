#!/usr/bin/env python3
"""Multimodal Fixtures — validation tests"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir(project_root):
    return project_root / "tests" / "fixtures" / "multimodal"


class TestImageFixtures:

    def test_all_referenced_image_fixtures_exist(self, fixtures_dir):
        expected = [
            "dashboard-latency-spike-001.json",
            "dashboard-kafka-lag-001.json",
            "diagram-inference-platform-001.json",
            "chart-throughput-001.json",
            "grafana-error-rate-001.json",
            "architecture-dual-path-001.json",
        ]
        for name in expected:
            path = fixtures_dir / "images" / name
            assert path.exists(), f"Missing fixture: {path}"

    def test_image_fixtures_are_valid_json(self, fixtures_dir):
        for path in (fixtures_dir / "images").glob("*.json"):
            data = json.loads(path.read_text())
            assert "fixture_id" in data
            assert "type" in data
            assert "description" in data
            assert "visual_elements" in data

    def test_image_fixtures_have_expected_tags(self, fixtures_dir):
        for path in (fixtures_dir / "images").glob("*.json"):
            data = json.loads(path.read_text())
            assert "expected_tags" in data
            assert len(data["expected_tags"]) > 0


class TestDocumentFixtures:

    def test_all_referenced_document_fixtures_exist(self, fixtures_dir):
        expected = [
            "incident-report-page-001.json",
            "architecture-doc-page-001.json",
            "deployment-guide-page-001.json",
        ]
        for name in expected:
            path = fixtures_dir / "documents" / name
            assert path.exists(), f"Missing fixture: {path}"

    def test_document_fixtures_are_valid_json(self, fixtures_dir):
        for path in (fixtures_dir / "documents").glob("*.json"):
            data = json.loads(path.read_text())
            assert "fixture_id" in data
            assert "type" in data
            assert "page_count" in data
            assert "sections" in data
            assert data["page_count"] == len(data["sections"])

    def test_document_fixtures_have_sections(self, fixtures_dir):
        for path in (fixtures_dir / "documents").glob("*.json"):
            data = json.loads(path.read_text())
            for section in data["sections"]:
                assert "page" in section
                assert "title" in section
