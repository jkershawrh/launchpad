#!/usr/bin/env python3
"""
Tests for Container Build/Push Script (Work Item 7.3)

TDD Phase: RED - Tests written first, expected to fail initially.
"""

import os
import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def build_script(project_root) -> Path:
    return project_root / "scripts" / "build-images.sh"


class TestScriptStructure:
    """Test build script file structure"""

    def test_build_script_exists(self, build_script):
        """Build script should exist"""
        assert build_script.exists(), f"build-images.sh not found at {build_script}"

    def test_build_script_is_executable(self, build_script):
        """Build script should be executable"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        assert os.access(build_script, os.X_OK), "build-images.sh should be executable"

    def test_build_script_has_bash_shebang(self, build_script):
        """Build script should have bash shebang"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        content = build_script.read_text()
        first_line = content.split('\n')[0]
        assert 'bash' in first_line, "First line should be a bash shebang"

    def test_build_script_has_help_flag(self, build_script):
        """Build script should support --help"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        result = subprocess.run(
            [str(build_script), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0, f"--help should exit 0, got {result.returncode}"
        output = (result.stdout + result.stderr).lower()
        assert 'usage' in output or 'help' in output, \
            "--help output should contain usage information"

    def test_build_script_has_strict_mode(self, build_script):
        """Build script should use set -euo pipefail"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        content = build_script.read_text()
        assert 'set -euo pipefail' in content, \
            "Script should use strict mode (set -euo pipefail)"


class TestBuildCapability:
    """Test build functionality"""

    def test_help_shows_cpu_target(self, build_script):
        """Help output should mention cpu as a build target"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        result = subprocess.run(
            [str(build_script), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        output = (result.stdout + result.stderr).lower()
        assert 'cpu' in output, "--help should mention cpu target"

    def test_help_shows_gaudi_target(self, build_script):
        """Help output should mention gaudi as a build target"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        result = subprocess.run(
            [str(build_script), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        output = (result.stdout + result.stderr).lower()
        assert 'gaudi' in output, "--help should mention gaudi target"

    def test_dry_run_cpu_succeeds(self, build_script):
        """Dry run for CPU target should succeed"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        result = subprocess.run(
            [str(build_script), "--target", "cpu", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0, \
            f"--target cpu --dry-run failed: {result.stderr}"

    def test_dry_run_gaudi_succeeds(self, build_script):
        """Dry run for Gaudi target should succeed"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        result = subprocess.run(
            [str(build_script), "--target", "gaudi", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0, \
            f"--target gaudi --dry-run failed: {result.stderr}"


class TestPushCapability:
    """Test push functionality"""

    def test_help_shows_registry_flag(self, build_script):
        """Help output should mention --registry flag"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        result = subprocess.run(
            [str(build_script), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        output = result.stdout + result.stderr
        assert '--registry' in output, "--help should mention --registry flag"

    def test_help_shows_tag_flag(self, build_script):
        """Help output should mention --tag flag"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        result = subprocess.run(
            [str(build_script), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        output = result.stdout + result.stderr
        assert '--tag' in output, "--help should mention --tag flag"

    def test_dry_run_push_shows_registry(self, build_script):
        """Dry run with --push should show registry URL"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        result = subprocess.run(
            [str(build_script), "--target", "cpu", "--push",
             "--registry", "quay.io/test-org", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0, f"Dry run push failed: {result.stderr}"
        output = result.stdout + result.stderr
        assert 'quay.io/test-org' in output, \
            "Dry run output should include the registry URL"


class TestImageNaming:
    """Test image naming conventions"""

    def test_script_references_cpu_image_name(self, build_script):
        """Script should reference vllm-cpu image name"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        content = build_script.read_text()
        assert 'vllm-cpu' in content, "Script should reference vllm-cpu image name"

    def test_script_references_gaudi_image_name(self, build_script):
        """Script should reference vllm-gaudi image name"""
        if not build_script.exists():
            pytest.skip("build-images.sh not created yet")

        content = build_script.read_text()
        assert 'vllm-gaudi' in content, "Script should reference vllm-gaudi image name"
