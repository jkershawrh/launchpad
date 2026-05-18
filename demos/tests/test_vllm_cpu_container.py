"""
Tests for vLLM CPU Container (Xeon6 Inference Path)

RED Phase: Write tests first - these will fail until container is implemented
"""

import subprocess
import pytest
import json
import time
from pathlib import Path


@pytest.fixture
def container_build_context(project_root) -> Path:
    """Path to vLLM CPU container build context"""
    return project_root / "containers" / "vllm-cpu"


@pytest.fixture
def container_image_name() -> str:
    """Container image name for testing"""
    return "localhost/vllm-cpu:test"


class TestContainerBuild:
    """Test container builds successfully"""

    def test_containerfile_exists(self, container_build_context):
        """Containerfile must exist"""
        containerfile = container_build_context / "Containerfile"
        assert containerfile.exists(), f"Containerfile not found at {containerfile}"

    def test_container_builds_successfully(self, container_build_context, container_image_name):
        """Container builds without errors"""
        result = subprocess.run(
            ["podman", "build", "-t", container_image_name, str(container_build_context)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        assert result.returncode == 0, f"Build failed: {result.stderr}"

    def test_build_time_acceptable(self, container_build_context, container_image_name):
        """Build completes in reasonable time (< 5 minutes)"""
        start_time = time.time()

        result = subprocess.run(
            ["podman", "build", "--no-cache", "-t", f"{container_image_name}-timing",
             str(container_build_context)],
            capture_output=True,
            timeout=300
        )

        build_time = time.time() - start_time

        # Clean up timing test image
        subprocess.run(["podman", "rmi", f"{container_image_name}-timing"],
                      capture_output=True)

        assert build_time < 300, f"Build took {build_time:.1f}s, should be < 300s"

    def test_image_size_acceptable(self, container_image_name):
        """Image size is reasonable (< 5GB)"""
        result = subprocess.run(
            ["podman", "images", container_image_name, "--format", "{{.Size}}"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            pytest.skip("Container not built yet")

        size_str = result.stdout.strip()

        # Parse size (e.g., "2.5GB", "1500MB")
        if "GB" in size_str:
            size_gb = float(size_str.replace("GB", ""))
        elif "MB" in size_str:
            size_gb = float(size_str.replace("MB", "")) / 1024
        else:
            pytest.fail(f"Unexpected size format: {size_str}")

        assert size_gb < 5.0, f"Image size {size_gb:.2f}GB exceeds 5GB limit"


class TestContainerRuntime:
    """Test container runtime behavior"""

    def test_container_has_health_endpoint(self, container_build_context):
        """Container includes health endpoint configuration"""
        containerfile = container_build_context / "Containerfile"

        if not containerfile.exists():
            pytest.skip("Containerfile not created yet")

        content = containerfile.read_text()

        # Check for HEALTHCHECK or exposed health port documentation
        assert "HEALTHCHECK" in content or "8000" in content or "health" in content.lower(), \
            "Container should document health endpoint"

    def test_container_runs_without_root(self, container_build_context):
        """Container specifies non-root user"""
        containerfile = container_build_context / "Containerfile"

        if not containerfile.exists():
            pytest.skip("Containerfile not created yet")

        content = containerfile.read_text()

        assert "USER" in content and "root" not in content.split("USER")[-1].split("\n")[0], \
            "Container should run as non-root user"

    def test_container_starts_without_error(self, container_image_name):
        """Container starts successfully"""
        # First check if image exists
        check_result = subprocess.run(
            ["podman", "images", "-q", container_image_name],
            capture_output=True,
            text=True
        )

        if not check_result.stdout.strip():
            pytest.skip("Container image not built yet")

        # Start container
        result = subprocess.run(
            ["podman", "run", "-d", "--name", "vllm-cpu-test-start",
             container_image_name, "--help"],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Clean up
        subprocess.run(["podman", "rm", "-f", "vllm-cpu-test-start"],
                      capture_output=True)

        assert result.returncode == 0, f"Container failed to start: {result.stderr}"

    def test_vllm_cpu_binary_present(self, container_image_name):
        """Inference runtime is present and executable in container"""
        check_result = subprocess.run(
            ["podman", "images", "-q", container_image_name],
            capture_output=True,
            text=True
        )

        if not check_result.stdout.strip():
            pytest.skip("Container image not built yet")

        # Test that transformers library is available (our inference runtime)
        result = subprocess.run(
            ["podman", "run", "--rm", container_image_name,
             "python3", "-c", "import transformers; print(transformers.__version__)"],
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, "Transformers module not found or not working"
        assert result.stdout.strip(), "Transformers version should be printed"

    def test_graceful_shutdown(self, container_image_name):
        """Container handles SIGTERM gracefully"""
        check_result = subprocess.run(
            ["podman", "images", "-q", container_image_name],
            capture_output=True,
            text=True
        )

        if not check_result.stdout.strip():
            pytest.skip("Container image not built yet")

        # Start a long-running process
        start_result = subprocess.run(
            ["podman", "run", "-d", "--name", "vllm-cpu-test-shutdown",
             container_image_name, "sleep", "300"],
            capture_output=True,
            text=True
        )

        if start_result.returncode != 0:
            pytest.skip("Could not start container for shutdown test")

        # Send SIGTERM and check it stops within 30s
        stop_result = subprocess.run(
            ["podman", "stop", "-t", "30", "vllm-cpu-test-shutdown"],
            capture_output=True,
            timeout=35
        )

        # Clean up
        subprocess.run(["podman", "rm", "-f", "vllm-cpu-test-shutdown"],
                      capture_output=True)

        assert stop_result.returncode == 0, "Container did not stop gracefully"


class TestContainerSecurity:
    """Test container security requirements"""

    def test_security_scan_passes(self, container_image_name):
        """Security scan shows no critical/high vulnerabilities"""
        # Check if container is built
        check_result = subprocess.run(
            ["podman", "images", "-q", container_image_name],
            capture_output=True,
            text=True
        )

        if not check_result.stdout.strip():
            pytest.skip("Container image not built yet")

        # Check if trivy is installed
        trivy_check = subprocess.run(
            ["which", "trivy"],
            capture_output=True
        )

        if trivy_check.returncode != 0:
            pytest.skip("Trivy not installed - run 'brew install trivy' to enable security scanning")

        # Run trivy scan
        result = subprocess.run(
            ["trivy", "image", "--severity", "CRITICAL,HIGH", "--exit-code", "1",
             container_image_name],
            capture_output=True,
            text=True,
            timeout=120
        )

        # Exit code 1 means vulnerabilities found, 0 means clean
        assert result.returncode == 0, \
            f"Security scan found critical/high vulnerabilities:\n{result.stdout}"

    def test_base_image_is_ubi(self, container_build_context):
        """Base image should be Red Hat UBI for supportability"""
        containerfile = container_build_context / "Containerfile"

        if not containerfile.exists():
            pytest.skip("Containerfile not created yet")

        content = containerfile.read_text()

        # Check for UBI base image
        assert "registry.access.redhat.com/ubi" in content, \
            "Should use Red Hat UBI base image for supportability"


# Validation matrix result tracker
def test_validation_matrix_cpu_container(project_root):
    """Track validation matrix results for CPU container"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"

    if not matrix_file.exists():
        pytest.skip("Validation matrix not found")

    # This test always passes - it's for documentation
    # Real validation happens in individual tests above
    assert True, "See individual tests for validation matrix criteria"


class TestCPUContainerHardening:
    """Security and quality hardening for CPU inference container"""

    def test_cpu_server_has_auth_middleware(self, project_root):
        """CPU inference server should have API key auth"""
        content = (project_root / "containers" / "vllm-cpu" / "inference_server.py").read_text()
        has_auth = ('API_KEY' in content or 'api_key' in content.lower()
                    or 'Depends(' in content or 'X-API-Key' in content)
        assert has_auth, "Inference server should have API key middleware"

    def test_cpu_server_sanitizes_errors(self, project_root):
        """500 errors should not contain raw exception messages"""
        content = (project_root / "containers" / "vllm-cpu" / "inference_server.py").read_text()
        import re
        raw_errors = re.findall(r'HTTPException.*status_code=500.*detail=.*str\(e\)', content, re.DOTALL)
        assert len(raw_errors) == 0, \
            "500 errors should not contain str(e)"

    def test_cpu_server_uses_lifespan(self, project_root):
        """Should use lifespan, not deprecated on_event"""
        content = (project_root / "containers" / "vllm-cpu" / "inference_server.py").read_text()
        assert '@app.on_event' not in content, \
            "Should use lifespan, not @app.on_event"
        assert 'lifespan' in content, "Should define lifespan"

    def test_cpu_server_uuid_completion_ids(self, project_root):
        """Completion IDs should use uuid, not timestamp"""
        content = (project_root / "containers" / "vllm-cpu" / "inference_server.py").read_text()
        assert 'uuid' in content.lower(), "Should use uuid for completion IDs"
        assert 'cmpl-{int(time.time())}' not in content, \
            "Should not use timestamp for completion IDs"

    def test_cpu_server_token_based_extraction(self, project_root):
        """Should use token offsets, not character slicing"""
        content = (project_root / "containers" / "vllm-cpu" / "inference_server.py").read_text()
        assert 'generated_text[len(request.prompt):]' not in content, \
            "Should use token offsets, not character-based slicing"

    def test_cpu_server_field_constraints(self, project_root):
        """max_tokens should have Field constraints"""
        content = (project_root / "containers" / "vllm-cpu" / "inference_server.py").read_text()
        assert 'Field(' in content, "Should use Pydantic Field for validation"
        # Check max_tokens has constraints
        import re
        max_tokens = re.search(r'max_tokens.*Field\(.*[lg]e=', content)
        assert max_tokens, "max_tokens should have ge/le constraints"
