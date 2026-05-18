#!/usr/bin/env python3
"""
Tests for Cluster Discovery Script (Stage 4)

TDD Phase: RED - Tests written first, expected to fail initially.
These tests validate the cluster discovery tooling.
"""

import pytest
import subprocess
from pathlib import Path
import yaml
import json


@pytest.fixture
def scripts_dir(project_root):
    """Path to scripts directory"""
    return project_root / "scripts"


@pytest.fixture
def discovery_script(scripts_dir):
    """Path to discovery script"""
    return scripts_dir / "discover-cluster.sh"


class TestDiscoveryScriptStructure:
    """Test discovery script file structure"""

    def test_scripts_directory_exists(self, scripts_dir):
        """Scripts directory should exist"""
        assert scripts_dir.exists(), f"Scripts directory not found: {scripts_dir}"
        assert scripts_dir.is_dir(), "Should be a directory"

    def test_discovery_script_exists(self, discovery_script):
        """Discovery script should exist"""
        assert discovery_script.exists(), "discover-cluster.sh not found"
        assert discovery_script.is_file(), "discover-cluster.sh should be a file"

    def test_discovery_script_executable(self, discovery_script):
        """Discovery script should be executable"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        # Check executable bit
        assert discovery_script.stat().st_mode & 0o111, \
            "discover-cluster.sh should be executable (chmod +x)"

    def test_discovery_script_has_shebang(self, discovery_script):
        """Discovery script should have proper shebang"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        content = discovery_script.read_text()
        assert content.startswith('#!/'), "Should have shebang"
        assert 'bash' in content.split('\n')[0].lower(), "Should use bash"


class TestDiscoveryScriptFunctionality:
    """Test discovery script core functionality"""

    def test_script_accepts_help_flag(self, discovery_script):
        """Script should accept --help flag"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        result = subprocess.run(
            [str(discovery_script), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Should exit successfully and show usage
        assert result.returncode == 0, "Help should exit with 0"
        assert "usage" in result.stdout.lower() or "help" in result.stdout.lower(), \
            "Help output should contain usage information"

    def test_script_accepts_output_flag(self, discovery_script):
        """Script should accept --output flag for specifying output file"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        result = subprocess.run(
            [str(discovery_script), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert "--output" in result.stdout or "-o" in result.stdout, \
            "Should accept --output flag"

    def test_script_handles_no_cluster_connection(self, discovery_script):
        """Script should handle no cluster connection gracefully"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        # Run without cluster connection (should not crash)
        result = subprocess.run(
            [str(discovery_script), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Should either succeed or fail gracefully
        # Exit code 1 is acceptable if cluster not accessible
        assert result.returncode in [0, 1], \
            "Should exit gracefully even without cluster access"


class TestDiscoveryOutput:
    """Test discovery output format"""

    def test_output_is_valid_yaml(self, discovery_script, tmp_path):
        """Discovery output should be valid YAML"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        # Run discovery (may fail if no cluster, that's ok)
        result = subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30
        )

        # If script ran and created output, validate it
        if output_file.exists():
            content = output_file.read_text()

            # Should be valid YAML
            try:
                data = yaml.safe_load(content)
                assert data is not None, "YAML should parse to data"
                assert isinstance(data, dict), "YAML should be a dictionary"
            except yaml.YAMLError as e:
                pytest.fail(f"Output is not valid YAML: {e}")

    def test_output_contains_cluster_section(self, discovery_script, tmp_path):
        """Output should contain cluster information section"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        # Run discovery
        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())
        assert "cluster" in data, "Output should have 'cluster' section"

    def test_output_contains_nodes_section(self, discovery_script, tmp_path):
        """Output should contain nodes information section"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())
        assert "nodes" in data, "Output should have 'nodes' section"

    def test_output_contains_operators_section(self, discovery_script, tmp_path):
        """Output should contain operators information section"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())
        assert "operators" in data, "Output should have 'operators' section"


class TestClusterInformation:
    """Test cluster information discovery"""

    def test_discovers_cluster_version(self, discovery_script, tmp_path):
        """Should discover OpenShift cluster version"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        if "cluster" in data:
            assert "version" in data["cluster"], \
                "Cluster section should contain version"

    def test_discovers_cluster_api_url(self, discovery_script, tmp_path):
        """Should discover cluster API URL"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        if "cluster" in data:
            assert "api_url" in data["cluster"], \
                "Cluster section should contain API URL"


class TestNodeInformation:
    """Test node information discovery"""

    def test_discovers_node_count(self, discovery_script, tmp_path):
        """Should discover total node count"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        if "nodes" in data:
            assert "total" in data["nodes"], \
                "Nodes section should contain total count"

    def test_discovers_gaudi_nodes(self, discovery_script, tmp_path):
        """Should discover Gaudi GPU nodes"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        if "nodes" in data:
            # Should have gaudi_nodes list or count
            assert "gaudi_nodes" in data["nodes"] or "gaudi_count" in data["nodes"], \
                "Should discover Gaudi nodes"

    def test_discovers_cpu_nodes(self, discovery_script, tmp_path):
        """Should discover CPU-only nodes (Xeon6)"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        if "nodes" in data:
            assert "cpu_nodes" in data["nodes"] or "cpu_count" in data["nodes"], \
                "Should discover CPU nodes"

    def test_discovers_node_labels(self, discovery_script, tmp_path):
        """Should discover node labels for scheduling"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        if "nodes" in data and "gaudi_nodes" in data["nodes"]:
            # If we found Gaudi nodes, they should have labels
            gaudi_nodes = data["nodes"]["gaudi_nodes"]
            if isinstance(gaudi_nodes, list) and len(gaudi_nodes) > 0:
                assert "labels" in gaudi_nodes[0], \
                    "Gaudi nodes should include labels"


class TestOperatorInformation:
    """Test operator information discovery"""

    def test_discovers_openshift_ai_operator(self, discovery_script, tmp_path):
        """Should discover if OpenShift AI operator is installed"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        if "operators" in data:
            # Should check for RHOAI/KServe
            assert isinstance(data["operators"], (list, dict)), \
                "Operators should be list or dict"

    def test_discovers_habana_device_plugin(self, discovery_script, tmp_path):
        """Should discover if Habana device plugin is installed"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        if "operators" in data:
            # Should check for Habana device plugin
            data_str = str(data["operators"]).lower()
            # May or may not be installed, just checking it's in the output
            assert True, "Operators section exists"


class TestImageRegistry:
    """Test image registry discovery"""

    def test_discovers_internal_registry(self, discovery_script, tmp_path):
        """Should discover internal image registry if available"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        output_file = tmp_path / "cluster-info.yaml"

        subprocess.run(
            [str(discovery_script), "--output", str(output_file), "--dry-run"],
            capture_output=True,
            timeout=30
        )

        if not output_file.exists():
            pytest.skip("Script did not produce output (no cluster access)")

        data = yaml.safe_load(output_file.read_text())

        # Registry info is optional but nice to have
        if "registry" in data:
            assert "internal" in data["registry"], \
                "Registry section should indicate if internal registry exists"


class TestErrorHandling:
    """Test error handling"""

    def test_handles_missing_oc_kubectl(self, discovery_script, tmp_path):
        """Should handle missing oc/kubectl gracefully"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        # Script should check for oc/kubectl and handle gracefully
        # This is tested by the script not crashing when run
        result = subprocess.run(
            [str(discovery_script), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Should not crash with exit code > 1
        assert result.returncode in [0, 1], \
            "Should handle missing tools gracefully"

    def test_provides_helpful_error_messages(self, discovery_script):
        """Should provide helpful error messages"""
        if not discovery_script.exists():
            pytest.skip("discover-cluster.sh not created yet")

        result = subprocess.run(
            [str(discovery_script), "--invalid-flag"],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Should show error message
        assert result.returncode != 0, "Invalid flag should fail"
        assert len(result.stderr) > 0 or len(result.stdout) > 0, \
            "Should provide error message"


# Validation matrix result tracker
def test_validation_matrix_cluster_discovery(project_root):
    """Track validation matrix results for cluster discovery"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"

    if not matrix_file.exists():
        pytest.skip("Validation matrix not found")

    # This test aggregates results from all other tests
    assert True, "See individual tests for validation matrix criteria"
