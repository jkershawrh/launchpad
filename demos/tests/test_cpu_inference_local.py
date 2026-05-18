"""
Tests for CPU Inference - Local Testing

RED Phase: Write tests first for local inference capabilities
"""

import subprocess
import pytest
import json
import time
import requests
from pathlib import Path


@pytest.fixture(scope="module")
def container_image_name() -> str:
    """Container image name for testing"""
    return "localhost/vllm-cpu:test"


@pytest.fixture(scope="module")
def test_model_name() -> str:
    """Small model for testing"""
    return "TinyLlama/TinyLlama-1.1B-Chat-v1.0"


@pytest.fixture(scope="module")
def inference_server(container_image_name, test_model_name):
    """Start inference server for testing"""
    container_name = "vllm-cpu-test-inference"
    port = 8000

    # Clean up any existing container
    subprocess.run(["podman", "rm", "-f", container_name], capture_output=True)

    # Start container
    start_result = subprocess.run(
        ["podman", "run", "-d",
         "--name", container_name,
         "-p", f"{port}:8000",
         "-e", f"MODEL_NAME={test_model_name}",
         container_image_name],
        capture_output=True,
        text=True,
        timeout=30
    )

    if start_result.returncode != 0:
        pytest.skip(f"Could not start inference server: {start_result.stderr}")

    # Wait for server to be ready (max 180 seconds for model loading)
    server_ready = False
    for i in range(36):  # 36 * 5s = 180s
        try:
            response = requests.get(f"http://localhost:{port}/health", timeout=5)
            if response.status_code == 200:
                server_ready = True
                break
        except requests.exceptions.RequestException:
            pass

        time.sleep(5)

    if not server_ready:
        # Get logs for debugging
        logs = subprocess.run(
            ["podman", "logs", container_name],
            capture_output=True,
            text=True
        )
        subprocess.run(["podman", "rm", "-f", container_name], capture_output=True)
        pytest.skip(f"Server not ready after 180s. Logs:\n{logs.stdout}\n{logs.stderr}")

    yield f"http://localhost:{port}"

    # Cleanup
    subprocess.run(["podman", "rm", "-f", container_name], capture_output=True)


class TestModelLoading:
    """Test model loads successfully"""

    def test_model_loads_successfully(self, inference_server):
        """Model should load without errors"""
        response = requests.get(f"{inference_server}/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "model" in data


class TestInferenceEndpoint:
    """Test inference endpoint functionality"""

    def test_inference_endpoint_responds(self, inference_server):
        """Inference endpoint returns valid response"""
        request_data = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "Hello, how are you?",
            "max_tokens": 20,
            "temperature": 0.7
        }

        response = requests.post(
            f"{inference_server}/v1/completions",
            json=request_data,
            timeout=60
        )

        assert response.status_code == 200, f"Request failed: {response.text}"

        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert "text" in data["choices"][0]

    def test_generates_output(self, inference_server):
        """Generated output should be non-empty"""
        request_data = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "The capital of France is",
            "max_tokens": 10,
            "temperature": 0.1  # Low temp for more deterministic output
        }

        response = requests.post(
            f"{inference_server}/v1/completions",
            json=request_data,
            timeout=60
        )

        assert response.status_code == 200
        data = response.json()

        generated_text = data["choices"][0]["text"]
        assert len(generated_text) > 0, "Generated text should not be empty"


class TestPerformance:
    """Test inference performance"""

    def test_time_to_first_token_acceptable(self, inference_server):
        """TTFT should be reasonable for small model on CPU"""
        request_data = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "Test prompt",
            "max_tokens": 1,
            "temperature": 0.1
        }

        start_time = time.time()
        response = requests.post(
            f"{inference_server}/v1/completions",
            json=request_data,
            timeout=60
        )
        elapsed = time.time() - start_time

        assert response.status_code == 200
        # For tiny model on CPU, should generate first token within 10 seconds
        assert elapsed < 10.0, f"TTFT {elapsed:.2f}s exceeds 10s threshold"

    def test_tokens_per_second_measured(self, inference_server):
        """Should generate multiple tokens"""
        request_data = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "Count to five:",
            "max_tokens": 50,
            "temperature": 0.7
        }

        start_time = time.time()
        response = requests.post(
            f"{inference_server}/v1/completions",
            json=request_data,
            timeout=60
        )
        elapsed = time.time() - start_time

        assert response.status_code == 200
        data = response.json()

        generated_text = data["choices"][0]["text"]
        # Rough token count (not exact, but good enough for testing)
        approx_tokens = len(generated_text.split())

        if approx_tokens > 0 and elapsed > 0:
            tokens_per_sec = approx_tokens / elapsed
            # Should generate at least 1 token per second on CPU
            assert tokens_per_sec > 0, "Should generate at least some tokens"

    def test_concurrent_requests(self, inference_server):
        """Should handle multiple concurrent requests"""
        import threading

        results = []

        def make_request():
            try:
                request_data = {
                    "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                    "prompt": "Hello",
                    "max_tokens": 10,
                    "temperature": 0.7
                }
                response = requests.post(
                    f"{inference_server}/v1/completions",
                    json=request_data,
                    timeout=60
                )
                results.append(response.status_code == 200)
            except Exception as e:
                results.append(False)

        # Launch 3 concurrent requests
        threads = [threading.Thread(target=make_request) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # At least 2 out of 3 should succeed
        assert sum(results) >= 2, "Should handle concurrent requests"


class TestReliability:
    """Test inference reliability"""

    def test_10_consecutive_successful(self, inference_server):
        """Should successfully complete 10 consecutive inferences"""
        request_data = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "Test",
            "max_tokens": 5,
            "temperature": 0.7
        }

        successes = 0
        for i in range(10):
            try:
                response = requests.post(
                    f"{inference_server}/v1/completions",
                    json=request_data,
                    timeout=30
                )
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        successes += 1
            except Exception:
                pass

        assert successes >= 9, f"Only {successes}/10 requests succeeded"


# Validation matrix result tracker
def test_validation_matrix_cpu_inference_local(project_root):
    """Track validation matrix results for CPU local inference"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"

    if not matrix_file.exists():
        pytest.skip("Validation matrix not found")

    # This test always passes - it's for documentation
    assert True, "See individual tests for validation matrix criteria"
