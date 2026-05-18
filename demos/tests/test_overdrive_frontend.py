#!/usr/bin/env python3
"""Tests for Overdrive frontend page structure."""
import pytest
import json
from pathlib import Path


@pytest.fixture
def frontend_dir(project_root):
    return project_root / "frontend"


@pytest.fixture
def src_dir(frontend_dir):
    return frontend_dir / "src"


class TestOverdrivePage:
    def test_overdrive_page_exists(self, src_dir):
        assert (src_dir / "pages" / "Overdrive.tsx").exists()

    def test_overdrive_compiles_in_build(self, src_dir):
        content = (src_dir / "pages" / "Overdrive.tsx").read_text()
        assert len(content) > 100, "Overdrive.tsx should not be empty"

    def test_overdrive_in_app_routes(self, src_dir):
        content = (src_dir / "App.tsx").read_text()
        assert '/overdrive' in content
        assert 'Overdrive' in content

    def test_overdrive_in_navigation(self, src_dir):
        content = (src_dir / "components" / "AppLayout.tsx").read_text()
        assert 'overdrive' in content.lower()

    def test_overdrive_has_infrastructure_section(self, src_dir):
        content = (src_dir / "pages" / "Overdrive.tsx").read_text()
        assert 'See Your Infrastructure' in content

    def test_overdrive_has_route_evaluator(self, src_dir):
        content = (src_dir / "pages" / "Overdrive.tsx").read_text()
        assert 'Route a Request' in content
        assert 'Evaluate Route' in content

    def test_overdrive_has_batch_demo(self, src_dir):
        content = (src_dir / "pages" / "Overdrive.tsx").read_text()
        assert 'Run Batch Demo' in content

    def test_overdrive_has_failover_demo(self, src_dir):
        content = (src_dir / "pages" / "Overdrive.tsx").read_text()
        assert 'Simulate' in content

    def test_overdrive_has_scale_section(self, src_dir):
        content = (src_dir / "pages" / "Overdrive.tsx").read_text()
        assert 'See It at Scale' in content

    def test_overdrive_uses_patternfly(self, src_dir):
        content = (src_dir / "pages" / "Overdrive.tsx").read_text()
        assert '@patternfly/react-core' in content

    def test_overdrive_uses_redhat_theme(self, src_dir):
        content = (src_dir / "pages" / "Overdrive.tsx").read_text()
        assert 'rh-color' in content


class TestOverdriveAPIClient:
    def test_client_has_overdrive_route(self, src_dir):
        content = (src_dir / "api" / "client.ts").read_text()
        assert 'overdriveRoute' in content

    def test_client_has_overdrive_batch(self, src_dir):
        content = (src_dir / "api" / "client.ts").read_text()
        assert 'overdriveBatch' in content

    def test_client_has_overdrive_status(self, src_dir):
        content = (src_dir / "api" / "client.ts").read_text()
        assert 'overdriveStatus' in content

    def test_client_has_overdrive_set_health(self, src_dir):
        content = (src_dir / "api" / "client.ts").read_text()
        assert 'overdriveSetHealth' in content

    def test_batch_wraps_in_requests_object(self, src_dir):
        content = (src_dir / "api" / "client.ts").read_text()
        assert '{ requests }' in content or 'requests:' in content
