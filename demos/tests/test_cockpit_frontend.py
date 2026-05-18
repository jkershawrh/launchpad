#!/usr/bin/env python3
"""Cockpit Dashboard — TDD Red Phase"""

import pytest
from pathlib import Path


@pytest.fixture
def frontend_src(project_root):
    return project_root / "frontend" / "src"


class TestCockpitPageExists:

    def test_page_file_exists(self, frontend_src):
        assert (frontend_src / "pages" / "CockpitDashboard.tsx").exists()

    def test_page_exports_default(self, frontend_src):
        content = (frontend_src / "pages" / "CockpitDashboard.tsx").read_text()
        assert "export default" in content


class TestCockpitRoute:

    def test_app_imports_cockpit(self, frontend_src):
        app = (frontend_src / "App.tsx").read_text()
        assert "CockpitDashboard" in app

    def test_app_has_cockpit_route(self, frontend_src):
        app = (frontend_src / "App.tsx").read_text()
        assert "/cockpit" in app


class TestCockpitNav:

    def test_nav_has_cockpit(self, frontend_src):
        layout = (frontend_src / "components" / "AppLayout.tsx").read_text()
        assert "/cockpit" in layout


class TestCockpitContent:

    def test_has_status_states(self, frontend_src):
        content = (frontend_src / "pages" / "CockpitDashboard.tsx").read_text()
        assert "RUNNING" in content
        assert "COMPLETE" in content

    def test_has_lane_cards(self, frontend_src):
        content = (frontend_src / "pages" / "CockpitDashboard.tsx").read_text()
        assert "XEON ECO" in content or "Xeon Eco" in content
        assert "GAUDI" in content

    def test_has_gauges(self, frontend_src):
        content = (frontend_src / "pages" / "CockpitDashboard.tsx").read_text()
        assert "req/s" in content.lower() or "requests" in content.lower()
        assert "tokens" in content.lower()
        assert "latency" in content.lower()

    def test_has_dark_theme(self, frontend_src):
        content = (frontend_src / "pages" / "CockpitDashboard.tsx").read_text()
        assert "#0a0a0a" in content or "#111" in content or "#0d0d0d" in content or "cockpit" in content.lower()

    def test_has_demo_selection(self, frontend_src):
        content = (frontend_src / "pages" / "CockpitDashboard.tsx").read_text()
        assert "Select a demo" in content
        assert "incident_storm" in content or "Incident Storm" in content
        assert "Run Again" in content


class TestCockpitCSS:

    def test_cockpit_css_exists(self, frontend_src):
        assert (frontend_src / "styles" / "cockpit.css").exists()
