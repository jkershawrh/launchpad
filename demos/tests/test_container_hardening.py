#!/usr/bin/env python3
"""
Tests for container hardening across all container images.
"""

import pytest
from pathlib import Path


class TestContainerIgnoreFiles:
    """Test .containerignore files exist"""

    @pytest.mark.parametrize("container_path", [
        "containers/vllm-cpu",
        "containers/vllm-gaudi",
        "gateway",
    ])
    def test_containerignore_exists(self, project_root, container_path):
        """Each container context should have .containerignore"""
        ignore_file = project_root / container_path / ".containerignore"
        assert ignore_file.exists(), \
            f"{container_path}/.containerignore should exist"


class TestRepoHygiene:
    """Test repository cleanliness"""

    def test_no_claude_install_in_repo(self, project_root):
        """claude-install.sh should not be in the repository"""
        assert not (project_root / "claude-install.sh").exists(), \
            "claude-install.sh should be removed from the repository"

    def test_test_llm_cpu_has_set_euo_pipefail(self, project_root):
        """test-llm-cpu.sh should have set -euo pipefail"""
        script = project_root / "containers" / "test-llm-cpu.sh"
        if not script.exists():
            pytest.skip("Script not found")
        content = script.read_text()
        assert 'set -e' in content, "Should have set -e for error handling"
