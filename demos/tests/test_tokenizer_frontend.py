#!/usr/bin/env python3
"""
Tests for Tokenizer frontend page wiring

TDD Red Phase: these tests should FAIL until the page is created.
"""

import pytest
from pathlib import Path


@pytest.fixture
def frontend_src(project_root) -> Path:
    return project_root / "frontend" / "src"


class TestTokenizerPageExists:

    def test_tokenizer_page_file_exists(self, frontend_src):
        page = frontend_src / "pages" / "Tokenizer.tsx"
        assert page.exists(), "frontend/src/pages/Tokenizer.tsx does not exist"

    def test_tokenizer_page_exports_default(self, frontend_src):
        page = frontend_src / "pages" / "Tokenizer.tsx"
        content = page.read_text()
        assert "export default" in content, "Tokenizer.tsx must have a default export"


class TestTokenizerRoute:

    def test_app_imports_tokenizer(self, frontend_src):
        app = (frontend_src / "App.tsx").read_text()
        assert "Tokenizer" in app, "App.tsx must import Tokenizer page"

    def test_app_has_tokenizer_route(self, frontend_src):
        app = (frontend_src / "App.tsx").read_text()
        assert "/tokenizer" in app, "App.tsx must define /tokenizer route"


class TestTokenizerNavItem:

    def test_nav_has_tokenizer(self, frontend_src):
        layout = (frontend_src / "components" / "AppLayout.tsx").read_text()
        assert "/tokenizer" in layout, "AppLayout.tsx must have /tokenizer nav item"

    def test_nav_label(self, frontend_src):
        layout = (frontend_src / "components" / "AppLayout.tsx").read_text()
        assert "Tokenizer" in layout or "tokenizer" in layout.lower(), \
            "AppLayout.tsx must have a Tokenizer nav label"


class TestTokenizerAPIMethod:

    def test_client_has_tokenize_method(self, frontend_src):
        client = (frontend_src / "api" / "client.ts").read_text()
        assert "tokenize" in client, "client.ts must have a tokenize API method"

    def test_client_tokenize_calls_correct_endpoint(self, frontend_src):
        client = (frontend_src / "api" / "client.ts").read_text()
        assert "/v1/tokenize" in client, "client.ts tokenize must call /v1/tokenize"
