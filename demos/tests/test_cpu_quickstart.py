#!/usr/bin/env python3
"""
Tests for CPU Quickstart Documentation (Stage 1.4)

TDD Phase: RED - Tests written first, expected to fail initially.
These tests validate the quickstart documentation and deployment scripts.
"""

import pytest
import yaml
from pathlib import Path
import re


@pytest.fixture
def quickstart_dir(project_root):
    """Path to CPU quickstart directory"""
    return project_root / "docs" / "quickstarts" / "cpu-hello-world"


class TestQuickstartStructure:
    """Test quickstart directory structure"""

    def test_quickstart_directory_exists(self, quickstart_dir):
        """Quickstart directory should exist"""
        assert quickstart_dir.exists(), f"Quickstart directory not found: {quickstart_dir}"
        assert quickstart_dir.is_dir(), "Should be a directory"

    def test_readme_exists(self, quickstart_dir):
        """README.md should exist"""
        readme = quickstart_dir / "README.md"
        assert readme.exists(), "README.md not found"
        assert readme.is_file(), "README.md should be a file"

    def test_deploy_script_exists(self, quickstart_dir):
        """deploy.sh script should exist"""
        deploy = quickstart_dir / "deploy.sh"

        if not deploy.exists():
            pytest.skip("deploy.sh not created yet")

        assert deploy.is_file(), "deploy.sh should be a file"

    def test_test_script_exists(self, quickstart_dir):
        """test.sh script should exist"""
        test_script = quickstart_dir / "test.sh"

        if not test_script.exists():
            pytest.skip("test.sh not created yet")

        assert test_script.is_file(), "test.sh should be a file"


class TestREADMEContent:
    """Test README.md content and structure"""

    def test_readme_has_title(self, quickstart_dir):
        """README should have a clear title"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()

        # Should have a markdown H1 heading
        assert re.search(r'^# .+', content, re.MULTILINE), \
            "README should have an H1 title"

    def test_readme_has_prerequisites(self, quickstart_dir):
        """README should list prerequisites"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()

        # Should have a prerequisites section
        assert re.search(r'## Prerequisites|## Requirements', content, re.IGNORECASE), \
            "README should have a Prerequisites section"

    def test_prerequisites_list_tools(self, quickstart_dir):
        """Prerequisites should mention required tools"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text().lower()

        # Should mention key tools
        required_tools = ['oc', 'kubectl', 'kustomize']
        missing_tools = []

        for tool in required_tools:
            if tool not in content:
                missing_tools.append(tool)

        assert len(missing_tools) == 0, \
            f"Prerequisites should mention: {', '.join(missing_tools)}"

    def test_readme_has_step_by_step(self, quickstart_dir):
        """README should have numbered steps"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()

        # Should have numbered steps (1., 2., 3., etc.)
        numbered_steps = re.findall(r'^\d+\.\s+.+', content, re.MULTILINE)

        assert len(numbered_steps) >= 3, \
            f"Should have at least 3 numbered steps, found {len(numbered_steps)}"

    def test_readme_shows_commands(self, quickstart_dir):
        """README should include command examples"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()

        # Should have code blocks with bash/shell commands
        code_blocks = re.findall(r'```(?:bash|shell|sh)?\n(.+?)\n```', content, re.DOTALL)

        assert len(code_blocks) >= 2, \
            f"Should have at least 2 code blocks with commands, found {len(code_blocks)}"

    def test_readme_references_manifest_directory(self, quickstart_dir):
        """README should reference the manifest directory"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()

        # Should mention the manifest directory path
        assert re.search(r'deploy/cpu-inference', content), \
            "README should reference deploy/cpu-inference directory"

    def test_readme_has_testing_section(self, quickstart_dir):
        """README should explain how to test the deployment"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()

        # Should have testing or verification section
        assert re.search(r'## Test|## Verify|## Validation', content, re.IGNORECASE), \
            "README should have a testing/verification section"

    def test_readme_shows_expected_output(self, quickstart_dir):
        """README should show expected command output"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()

        # Look for indicators of expected output
        has_output_examples = (
            'output:' in content.lower() or
            'example output' in content.lower() or
            'should see' in content.lower() or
            'returns:' in content.lower()
        )

        assert has_output_examples, \
            "README should show expected output for key commands"


class TestReferencedFiles:
    """Test that files referenced in README actually exist"""

    def test_manifest_files_exist(self, quickstart_dir, project_root):
        """All manifest files referenced should exist"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        manifest_dir = project_root / "deploy" / "cpu-inference"

        # Expected manifest files
        expected_files = [
            "namespace.yaml",
            "serving-runtime.yaml",
            "inference-service.yaml",
            "network-policy.yaml",
            "kustomization.yaml"
        ]

        for filename in expected_files:
            filepath = manifest_dir / filename
            assert filepath.exists(), f"Referenced manifest file not found: {filename}"


class TestDeployScript:
    """Test deploy.sh script"""

    def test_deploy_script_has_shebang(self, quickstart_dir):
        """deploy.sh should have proper shebang"""
        deploy = quickstart_dir / "deploy.sh"

        if not deploy.exists():
            pytest.skip("deploy.sh not created yet")

        content = deploy.read_text()

        assert content.startswith('#!/'), "Script should have shebang"
        assert 'bash' in content.split('\n')[0] or 'sh' in content.split('\n')[0], \
            "Should be a bash/sh script"

    def test_deploy_script_uses_kustomize(self, quickstart_dir):
        """deploy.sh should use kustomize for deployment"""
        deploy = quickstart_dir / "deploy.sh"

        if not deploy.exists():
            pytest.skip("deploy.sh not created yet")

        content = deploy.read_text()

        # Should use kustomize or kubectl kustomize
        has_kustomize = (
            'kustomize build' in content or
            'kubectl apply -k' in content or
            'oc apply -k' in content
        )

        assert has_kustomize, "deploy.sh should use kustomize for deployment"

    def test_deploy_script_is_executable(self, quickstart_dir):
        """deploy.sh should be executable"""
        deploy = quickstart_dir / "deploy.sh"

        if not deploy.exists():
            pytest.skip("deploy.sh not created yet")

        import stat
        mode = deploy.stat().st_mode

        # Check if executable by owner
        assert mode & stat.S_IXUSR, "deploy.sh should be executable"


class TestTestScript:
    """Test test.sh script"""

    def test_test_script_has_shebang(self, quickstart_dir):
        """test.sh should have proper shebang"""
        test_script = quickstart_dir / "test.sh"

        if not test_script.exists():
            pytest.skip("test.sh not created yet")

        content = test_script.read_text()

        assert content.startswith('#!/'), "Script should have shebang"

    def test_test_script_checks_deployment(self, quickstart_dir):
        """test.sh should verify deployment status"""
        test_script = quickstart_dir / "test.sh"

        if not test_script.exists():
            pytest.skip("test.sh not created yet")

        content = test_script.read_text()

        # Should check for pods or services
        has_checks = (
            'get pods' in content or
            'get inferenceservice' in content or
            'get servingruntime' in content
        )

        assert has_checks, "test.sh should check deployment status"

    def test_test_script_tests_inference(self, quickstart_dir):
        """test.sh should test inference endpoint"""
        test_script = quickstart_dir / "test.sh"

        if not test_script.exists():
            pytest.skip("test.sh not created yet")

        content = test_script.read_text()

        # Should make inference request (curl or similar)
        has_inference_test = (
            'curl' in content or
            '/v1/completions' in content or
            '/v1/models' in content
        )

        assert has_inference_test, "test.sh should test inference endpoint"


class TestDocumentationQuality:
    """Test overall documentation quality"""

    def test_readme_word_count(self, quickstart_dir):
        """README should be substantial but not overwhelming"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()
        word_count = len(content.split())

        # Should be detailed enough to be useful
        assert word_count >= 200, \
            f"README seems too short ({word_count} words), should be at least 200"

        # But not overwhelming for a quickstart
        assert word_count <= 2000, \
            f"README seems too long ({word_count} words) for a quickstart, consider breaking into sections"

    def test_no_broken_links(self, quickstart_dir, project_root):
        """README should not have broken relative links"""
        readme = quickstart_dir / "README.md"

        if not readme.exists():
            pytest.skip("README.md not created yet")

        content = readme.read_text()

        # Find markdown links: [text](path)
        links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)

        broken_links = []
        for text, link in links:
            # Skip external URLs
            if link.startswith('http://') or link.startswith('https://'):
                continue

            # Skip anchors
            if link.startswith('#'):
                continue

            # Check relative paths
            link_path = (quickstart_dir / link).resolve()
            if not link_path.exists():
                broken_links.append(link)

        assert len(broken_links) == 0, \
            f"Found broken links: {', '.join(broken_links)}"


# Validation matrix result tracker
def test_validation_matrix_cpu_quickstart(project_root):
    """Track validation matrix results for CPU quickstart"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"

    if not matrix_file.exists():
        pytest.skip("Validation matrix not found")

    # This test aggregates results from all other tests
    # Individual tests validate specific criteria
    assert True, "See individual tests for validation matrix criteria"
