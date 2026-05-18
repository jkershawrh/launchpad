#!/usr/bin/env python3
"""Stage 9: Workload Frontend — TDD Red Phase"""

import pytest
from pathlib import Path


@pytest.fixture
def frontend_src(project_root) -> Path:
    return project_root / "frontend" / "src"


class TestWorkloadPageExists:

    def test_page_file_exists(self, frontend_src):
        assert (frontend_src / "pages" / "WorkloadDemo.tsx").exists()

    def test_page_exports_default(self, frontend_src):
        content = (frontend_src / "pages" / "WorkloadDemo.tsx").read_text()
        assert "export default" in content


class TestWorkloadRoute:

    def test_app_imports_workload(self, frontend_src):
        app = (frontend_src / "App.tsx").read_text()
        assert "WorkloadDemo" in app

    def test_app_has_workload_route(self, frontend_src):
        app = (frontend_src / "App.tsx").read_text()
        assert "/workload" in app


class TestWorkloadNav:

    def test_nav_has_workload(self, frontend_src):
        layout = (frontend_src / "components" / "AppLayout.tsx").read_text()
        assert "/workload" in layout


class TestWorkloadAPI:

    def test_client_has_workload_run(self, frontend_src):
        client = (frontend_src / "api" / "client.ts").read_text()
        assert "workloadRun" in client or "workload" in client

    def test_client_calls_workload_endpoint(self, frontend_src):
        client = (frontend_src / "api" / "client.ts").read_text()
        assert "/v1/workload" in client
