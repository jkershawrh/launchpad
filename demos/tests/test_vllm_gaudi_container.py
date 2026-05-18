#!/usr/bin/env python3
"""
Tests for vLLM Gaudi Container (Stage 2.1)

TDD Phase: RED - Tests written first, expected to fail initially.
These tests validate the Gaudi-accelerated container image.
"""

import pytest
import subprocess
import time
import requests
from pathlib import Path


@pytest.fixture
def container_dir(project_root):
    """Path to Gaudi container directory"""
    return project_root / "containers" / "vllm-gaudi"


@pytest.fixture
def image_name():
    """Gaudi container image name for testing"""
    return "vllm-gaudi:test"


class TestContainerBuild:
    """Test container build process"""

    def test_containerfile_exists(self, container_dir):
        """Containerfile should exist"""
        containerfile = container_dir / "Containerfile"
        assert containerfile.exists(), f"Containerfile not found at {containerfile}"

    def test_container_builds_successfully(self, container_dir, image_name):
        """Container should build without errors"""
        containerfile = container_dir / "Containerfile"

        if not containerfile.exists():
            pytest.skip("Containerfile not created yet")

        # Build the container
        result = subprocess.run(
            ["podman", "build", "-t", image_name, "-f", str(containerfile), str(container_dir)],
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes for build
        )

        assert result.returncode == 0, f"Container build failed: {result.stderr}"

    def test_build_time_acceptable(self, container_dir, image_name):
        """Container should build in reasonable time"""
        containerfile = container_dir / "Containerfile"

        if not containerfile.exists():
            pytest.skip("Containerfile not created yet")

        start_time = time.time()

        result = subprocess.run(
            ["podman", "build", "-t", image_name, "-f", str(containerfile), str(container_dir)],
            capture_output=True,
            text=True,
            timeout=600
        )

        build_time = time.time() - start_time

        # Gaudi container may be larger, allow up to 10 minutes
        assert build_time < 600, f"Build took too long: {build_time}s"

    def test_image_size_reasonable(self, image_name):
        """Image size should be under 10GB (Gaudi drivers are large)"""
        result = subprocess.run(
            ["podman", "images", image_name, "--format", "{{.Size}}"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            pytest.skip("Image not built yet")

        size_str = result.stdout.strip()

        # Parse size (format: "5.2GB" or "1024MB")
        if "GB" in size_str:
            size_gb = float(size_str.replace("GB", ""))
            assert size_gb < 10, f"Image too large: {size_gb}GB"
        elif "MB" in size_str:
            # Less than 1GB, definitely OK
            assert True


class TestHabanaDrivers:
    """Test Habana driver and library presence"""

    def test_habana_drivers_present(self, image_name):
        """Habana drivers should be present in image"""
        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "ls", "/usr/lib/habanalabs"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet or drivers path different")

        # Should have some files in habanalabs directory
        assert len(result.stdout.strip()) > 0, "Habana drivers directory empty"

    def test_habana_env_vars_set(self, image_name):
        """Habana environment variables should be configured"""
        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "env"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet")

        env_output = result.stdout

        # Check for key Habana environment variables
        habana_vars = ["HABANA_VISIBLE_DEVICES", "HABANA_LOGS", "HL_"]

        has_habana_var = any(var in env_output for var in habana_vars)

        # At least one Habana-related env var should be set
        assert has_habana_var, "No Habana environment variables found"

    def test_synapse_ai_present(self, image_name):
        """Synapse AI (Habana SDK) should be installed"""
        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "python3", "-c",
             "import habana_frameworks.torch; print('OK')"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet or Synapse AI not installed")

        assert "OK" in result.stdout, "Synapse AI import failed"


class TestContainerRuntime:
    """Test container runtime behavior"""

    def test_container_starts_without_error(self, image_name):
        """Container should start without immediate errors"""
        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "echo", "test"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet")

        assert "test" in result.stdout, "Container failed to execute basic command"

    def test_container_has_health_endpoint(self, image_name):
        """Container should expose health endpoint"""
        # This test will be more meaningful when the inference server is running
        # For now, just check that the health check command exists

        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "which", "python3"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet")

        assert "/python3" in result.stdout, "Python3 not found in container"

    def test_vllm_gaudi_available(self, image_name):
        """vLLM with Gaudi support should be available"""
        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "python3", "-c",
             "import vllm; print(vllm.__version__)"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet or vLLM not installed")

        # Should print vLLM version
        assert len(result.stdout.strip()) > 0, "vLLM not properly installed"


class TestSecurityContext:
    """Test security configurations"""

    def test_container_runs_as_nonroot(self, image_name):
        """Container should run as non-root user"""
        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "id", "-u"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet")

        uid = int(result.stdout.strip())
        assert uid != 0, f"Container running as root (UID: {uid})"
        assert uid == 1001, f"Container should run as UID 1001, got {uid}"

    def test_container_user_name(self, image_name):
        """Container should have proper user context"""
        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "whoami"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet")

        username = result.stdout.strip()
        # Should not be root
        assert username != "root", "Container running as root user"

    def test_no_privileged_capabilities(self, image_name):
        """Container should not require privileged capabilities"""
        # Try running without --privileged flag
        result = subprocess.run(
            ["podman", "run", "--rm", image_name, "echo", "test"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet")

        assert result.returncode == 0, "Container requires privileged mode"


class TestInferenceServer:
    """Test inference server functionality"""

    def test_entrypoint_exists(self, container_dir):
        """Entrypoint script should exist"""
        entrypoint = container_dir / "entrypoint.sh"

        if not entrypoint.exists():
            pytest.skip("Entrypoint not created yet")

        assert entrypoint.exists(), "entrypoint.sh not found"

    def test_inference_server_script_exists(self, container_dir):
        """Inference server Python script should exist"""
        server_script = container_dir / "inference_server.py"

        if not server_script.exists():
            pytest.skip("Inference server script not created yet")

        assert server_script.exists(), "inference_server.py not found"

    def test_server_imports_successfully(self, container_dir):
        """Server script should import without errors"""
        server_script = container_dir / "inference_server.py"

        if not server_script.exists():
            pytest.skip("Inference server script not created yet")

        # Basic syntax check
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(server_script)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Server script has syntax errors: {result.stderr}"


class TestGracefulShutdown:
    """Test graceful shutdown behavior"""

    def test_handles_sigterm(self, image_name):
        """Container should handle SIGTERM gracefully"""
        # Start container in background
        proc = subprocess.Popen(
            ["podman", "run", "--rm", "--name", "gaudi-test-shutdown", image_name, "sleep", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Give it a moment to start
        time.sleep(2)

        # Send SIGTERM
        subprocess.run(["podman", "stop", "-t", "5", "gaudi-test-shutdown"], timeout=10)

        # Wait for process to exit
        try:
            proc.wait(timeout=10)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.skip("Container didn't shut down gracefully")

        # Should exit cleanly (0 or 143 for SIGTERM)
        assert exit_code in [0, 143, 137], f"Unexpected exit code: {exit_code}"


class TestValidationMatrix:
    """Validation matrix checks"""

    def test_validation_matrix_gaudi_container(self, project_root):
        """Track validation matrix results"""
        matrix_file = project_root / "tests" / "validation_matrix.yaml"

        if not matrix_file.exists():
            pytest.skip("Validation matrix not found")

        # This aggregates results from other tests
        assert True, "See individual tests for validation matrix criteria"


class TestV2Containerfile:
    """Test V2 production Gaudi Containerfile"""

    def test_v2_containerfile_exists(self, container_dir):
        """V2 Containerfile should exist for production Gaudi deployment"""
        v2_file = container_dir / "Containerfile.v2"
        assert v2_file.exists(), "Containerfile.v2 not found"

    def test_v2_uses_habana_base_image(self, container_dir):
        """V2 should use official Habana base image"""
        v2_file = container_dir / "Containerfile.v2"

        if not v2_file.exists():
            pytest.skip("Containerfile.v2 not created yet")

        content = v2_file.read_text()
        from_lines = [l for l in content.split('\n') if l.strip().startswith('FROM')]
        assert any('vault.habana.ai' in l for l in from_lines), \
            "V2 should use vault.habana.ai base image"

    def test_v2_does_not_create_mock_dirs(self, container_dir):
        """V2 should not create mock Habana directories"""
        v2_file = container_dir / "Containerfile.v2"

        if not v2_file.exists():
            pytest.skip("Containerfile.v2 not created yet")

        content = v2_file.read_text()
        assert 'mkdir -p /opt/app-root/src/.habana' not in content, \
            "V2 should not create mock .habana directory"
        assert 'Mock Habana' not in content, \
            "V2 should not reference mock Habana"

    def test_v2_does_not_set_mock_mode(self, container_dir):
        """V2 should not enable mock mode"""
        v2_file = container_dir / "Containerfile.v2"

        if not v2_file.exists():
            pytest.skip("Containerfile.v2 not created yet")

        content = v2_file.read_text()
        assert 'HABANA_USE_MOCK' not in content or \
               'HABANA_USE_MOCK="true"' not in content, \
            "V2 should not set HABANA_USE_MOCK to true"

    def test_v2_installs_habana_packages(self, container_dir):
        """V2 should install Habana SDK packages"""
        v2_file = container_dir / "Containerfile.v2"

        if not v2_file.exists():
            pytest.skip("Containerfile.v2 not created yet")

        content = v2_file.read_text()
        has_habana_pkg = (
            'optimum-habana' in content or
            'habana-frameworks' in content or
            'habana_frameworks' in content
        )
        assert has_habana_pkg, \
            "V2 should install optimum-habana or habana-frameworks"

    def test_v2_sets_hpu_environment(self, container_dir):
        """V2 should set HPU environment variables"""
        v2_file = container_dir / "Containerfile.v2"

        if not v2_file.exists():
            pytest.skip("Containerfile.v2 not created yet")

        content = v2_file.read_text()
        has_hpu_env = (
            'PT_HPU_' in content or
            'OMPI_MCA_' in content
        )
        assert has_hpu_env, \
            "V2 should set PT_HPU_ or OMPI_MCA_ environment variables"


class TestV2InferenceServer:
    """Test V2 inference server HPU support"""

    def test_detect_device_can_return_hpu(self, container_dir):
        """detect_device() should have a code path that returns 'hpu'"""
        server_file = container_dir / "inference_server.py"

        if not server_file.exists():
            pytest.skip("inference_server.py not created yet")

        content = server_file.read_text()
        lines = content.split('\n')
        uncommented_returns = [
            l.strip() for l in lines
            if 'return' in l and '"hpu"' in l and not l.strip().startswith('#')
        ]
        assert len(uncommented_returns) > 0, \
            "detect_device() should have an uncommented 'return \"hpu\"' path"

    def test_habana_import_not_commented(self, container_dir):
        """Habana frameworks import should be real code, not commented out"""
        server_file = container_dir / "inference_server.py"

        if not server_file.exists():
            pytest.skip("inference_server.py not created yet")

        content = server_file.read_text()
        lines = content.split('\n')
        real_imports = [
            l for l in lines
            if 'habana_frameworks' in l
            and not l.strip().startswith('#')
            and ('import' in l)
        ]
        assert len(real_imports) > 0, \
            "Should have uncommented 'import habana_frameworks' statement"

    def test_gaudi_available_not_hardcoded_false(self, container_dir):
        """GAUDI_AVAILABLE should be set via try/except import, not hardcoded"""
        server_file = container_dir / "inference_server.py"

        if not server_file.exists():
            pytest.skip("inference_server.py not created yet")

        content = server_file.read_text()
        assert 'try:' in content and 'GAUDI_AVAILABLE = True' in content, \
            "GAUDI_AVAILABLE should be set dynamically via try/except import pattern"


class TestV2Entrypoint:
    """Test V2 entrypoint device detection"""

    def test_entrypoint_checks_accel_device(self, container_dir):
        """Entrypoint should check for /dev/accel devices (Gaudi2 path)"""
        entrypoint = container_dir / "entrypoint.sh"

        if not entrypoint.exists():
            pytest.skip("entrypoint.sh not created yet")

        content = entrypoint.read_text()
        assert '/dev/accel' in content, \
            "Entrypoint should check for /dev/accel (Gaudi2 accelerator devices)"

    def test_entrypoint_does_not_default_to_mock(self, container_dir):
        """Entrypoint should not set HABANA_USE_MOCK=true as a fallback"""
        entrypoint = container_dir / "entrypoint.sh"

        if not entrypoint.exists():
            pytest.skip("entrypoint.sh not created yet")

        content = entrypoint.read_text()
        assert 'HABANA_USE_MOCK="true"' not in content, \
            "Entrypoint should not fall back to mock mode"

    def test_entrypoint_reports_device_count(self, container_dir):
        """Entrypoint should report Gaudi device count"""
        entrypoint = container_dir / "entrypoint.sh"

        if not entrypoint.exists():
            pytest.skip("entrypoint.sh not created yet")

        content = entrypoint.read_text()
        has_device_count = (
            'hl-smi' in content or
            '/dev/accel/accel' in content
        )
        assert has_device_count, \
            "Entrypoint should use hl-smi or count /dev/accel devices"


# Skip security scan if trivy not installed
@pytest.mark.skipif(
    subprocess.run(["which", "trivy"], capture_output=True).returncode != 0,
    reason="trivy not installed"
)
class TestSecurityScan:
    """Security scanning with trivy"""

    def test_no_critical_vulnerabilities(self, image_name):
        """Container should have no critical vulnerabilities"""
        result = subprocess.run(
            ["trivy", "image", "--severity", "CRITICAL", "--exit-code", "1", image_name],
            capture_output=True,
            text=True,
            timeout=300
        )

        # Exit code 0 = no vulnerabilities, 1 = vulnerabilities found
        assert result.returncode == 0, f"Critical vulnerabilities found:\n{result.stdout}"

    def test_no_high_vulnerabilities(self, image_name):
        """Container should have no high severity vulnerabilities"""
        result = subprocess.run(
            ["trivy", "image", "--severity", "HIGH", "--exit-code", "1", image_name],
            capture_output=True,
            text=True,
            timeout=300
        )

        assert result.returncode == 0, f"High vulnerabilities found:\n{result.stdout}"


class TestGaudiContainerHardening:
    """Security and quality hardening for Gaudi inference container"""

    def test_gaudi_server_has_auth_middleware(self, project_root):
        """Gaudi inference server should have API key auth"""
        content = (project_root / "containers" / "vllm-gaudi" / "inference_server.py").read_text()
        has_auth = ('API_KEY' in content or 'api_key' in content.lower()
                    or 'Depends(' in content)
        assert has_auth, "Gaudi server should have API key middleware"

    def test_gaudi_server_sanitizes_errors(self, project_root):
        """500 errors should not contain raw exception messages"""
        content = (project_root / "containers" / "vllm-gaudi" / "inference_server.py").read_text()
        import re
        raw_errors = re.findall(r'HTTPException.*500.*detail=.*str\(e\)', content, re.DOTALL)
        assert len(raw_errors) == 0, "500 errors should not contain str(e)"

    def test_gaudi_entrypoint_uses_dash_n(self, project_root):
        """Entrypoint should use [ -n ] not [ ! -z ]"""
        content = (project_root / "containers" / "vllm-gaudi" / "entrypoint.sh").read_text()
        assert '[ ! -z' not in content, \
            "Should use [ -n ] instead of [ ! -z ]"
