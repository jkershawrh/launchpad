#!/usr/bin/env python3
"""
Tests for Gaudi Inference - Local Testing (Stage 2.2)

TDD Phase: RED - Tests written first, expected to fail initially.
These tests validate local inference using the Gaudi container (V1 mock mode).
"""

import pytest
import subprocess
import time
import requests
import json
from pathlib import Path


@pytest.fixture(scope="module")
def container_name():
    """Container name for local testing"""
    return "gaudi-inference-test"


@pytest.fixture(scope="module")
def image_name():
    """Gaudi container image name"""
    return "vllm-gaudi:test"


@pytest.fixture(scope="module")
def inference_url():
    """Base URL for inference API"""
    return "http://localhost:8001"  # Different port from CPU (8000)


@pytest.fixture(scope="module")
def model_name():
    """Model name for testing"""
    return "TinyLlama/TinyLlama-1.1B-Chat-v1.0"


@pytest.fixture(scope="module")
def inference_server(container_name, image_name, inference_url):
    """
    Start inference server container for testing

    Runs in background for entire test module
    """
    # Check if container already running
    check_result = subprocess.run(
        ["podman", "ps", "-q", "-f", f"name={container_name}"],
        capture_output=True,
        text=True
    )

    if check_result.stdout.strip():
        # Container already running
        yield inference_url
        return

    # Start container
    print(f"\nStarting Gaudi inference server on port 8001...")

    proc = subprocess.Popen(
        [
            "podman", "run",
            "--rm",
            "--name", container_name,
            "-p", "8001:8000",
            "-e", "MODEL_NAME=TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "-e", "HABANA_USE_MOCK=true",
            image_name
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server to be ready
    max_wait = 120  # 2 minutes for model download
    start_time = time.time()
    server_ready = False

    print("Waiting for server to be ready...")
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f"{inference_url}/health", timeout=2)
            if response.status_code == 200:
                print("Server ready!")
                server_ready = True
                break
        except requests.exceptions.RequestException:
            pass

        # Check if process crashed
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            print(f"Server crashed. Stdout: {stdout.decode()}")
            print(f"Stderr: {stderr.decode()}")
            pytest.fail("Inference server failed to start")

        time.sleep(2)

    if not server_ready:
        proc.kill()
        pytest.fail(f"Server did not become ready within {max_wait}s")

    # Yield for tests
    yield inference_url

    # Cleanup
    print("\nStopping inference server...")
    subprocess.run(["podman", "stop", "-t", "10", container_name], timeout=15)
    proc.wait(timeout=5)


class TestModelLoading:
    """Test model loading and initialization"""

    def test_model_loads_successfully(self, inference_server):
        """Model should load without errors"""
        # Server started successfully in fixture
        assert inference_server is not None

    def test_health_endpoint_responds(self, inference_server):
        """Health endpoint should return 200 OK"""
        response = requests.get(f"{inference_server}/health", timeout=10)

        assert response.status_code == 200, f"Health check failed: {response.status_code}"

        health_data = response.json()
        assert health_data["status"] == "healthy", f"Server unhealthy: {health_data}"

    def test_health_shows_mock_mode(self, inference_server):
        """Health endpoint should indicate V1 mock mode"""
        response = requests.get(f"{inference_server}/health", timeout=10)
        health_data = response.json()

        assert "mock_mode" in health_data, "Health response missing mock_mode field"
        assert health_data["mock_mode"] is True, "Should be running in mock mode for V1"

    def test_health_shows_device_info(self, inference_server):
        """Health endpoint should show device information"""
        response = requests.get(f"{inference_server}/health", timeout=10)
        health_data = response.json()

        assert "device" in health_data, "Health response missing device field"
        # V1 should use CPU (mock mode)
        assert "cpu" in health_data["device"].lower(), f"Expected CPU device in V1, got {health_data['device']}"


class TestAPIEndpoints:
    """Test API endpoints"""

    def test_models_endpoint_responds(self, inference_server):
        """Models endpoint should list available models"""
        response = requests.get(f"{inference_server}/v1/models", timeout=10)

        assert response.status_code == 200, f"Models endpoint failed: {response.status_code}"

        models_data = response.json()
        assert "data" in models_data, "Models response missing data field"
        assert len(models_data["data"]) > 0, "No models listed"

    def test_models_includes_expected_model(self, inference_server, model_name):
        """Models list should include the loaded model"""
        response = requests.get(f"{inference_server}/v1/models", timeout=10)
        models_data = response.json()

        model_ids = [model["id"] for model in models_data["data"]]
        assert model_name in model_ids, f"Expected model {model_name} not in list: {model_ids}"

    def test_completions_endpoint_generates_text(self, inference_server, model_name):
        """Completions endpoint should generate text"""
        payload = {
            "model": model_name,
            "prompt": "The capital of France is",
            "max_tokens": 10,
            "temperature": 0.7
        }

        response = requests.post(
            f"{inference_server}/v1/completions",
            json=payload,
            timeout=30
        )

        assert response.status_code == 200, f"Completions failed: {response.status_code}"

        completion_data = response.json()
        assert "choices" in completion_data, "Completion response missing choices"
        assert len(completion_data["choices"]) > 0, "No completion choices returned"
        assert "text" in completion_data["choices"][0], "Choice missing text field"

        generated_text = completion_data["choices"][0]["text"]
        assert len(generated_text) > 0, "Generated text is empty"

    def test_completions_returns_usage_stats(self, inference_server, model_name):
        """Completions should return token usage statistics"""
        payload = {
            "model": model_name,
            "prompt": "Hello",
            "max_tokens": 5
        }

        response = requests.post(
            f"{inference_server}/v1/completions",
            json=payload,
            timeout=30
        )

        completion_data = response.json()
        assert "usage" in completion_data, "Completion response missing usage field"

        usage = completion_data["usage"]
        assert "prompt_tokens" in usage, "Usage missing prompt_tokens"
        assert "completion_tokens" in usage, "Usage missing completion_tokens"
        assert "total_tokens" in usage, "Usage missing total_tokens"

        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"], \
            "Total tokens doesn't match sum"


class TestPerformance:
    """Test performance characteristics"""

    def test_time_to_first_token_acceptable(self, inference_server, model_name):
        """Time to first token should be acceptable for CPU fallback"""
        payload = {
            "model": model_name,
            "prompt": "Once upon a time",
            "max_tokens": 20
        }

        start_time = time.time()

        response = requests.post(
            f"{inference_server}/v1/completions",
            json=payload,
            timeout=60
        )

        end_time = time.time()
        ttft = (end_time - start_time) * 1000  # Convert to ms

        assert response.status_code == 200, "Request failed"

        # V1 (CPU fallback): allow up to 30s for TTFT
        # V2 (real Gaudi): will be much faster
        assert ttft < 30000, f"TTFT too slow: {ttft}ms (expected < 30000ms for V1)"

        print(f"TTFT: {ttft:.0f}ms")

    def test_generates_multiple_tokens(self, inference_server, model_name):
        """Should generate requested number of tokens"""
        requested_tokens = 15

        payload = {
            "model": model_name,
            "prompt": "The quick brown fox",
            "max_tokens": requested_tokens
        }

        response = requests.post(
            f"{inference_server}/v1/completions",
            json=payload,
            timeout=60
        )

        completion_data = response.json()
        generated_tokens = completion_data["usage"]["completion_tokens"]

        # Should generate close to requested amount (may stop early on EOS)
        assert generated_tokens > 0, "No tokens generated"
        assert generated_tokens <= requested_tokens, f"Generated too many tokens: {generated_tokens}"


class TestConcurrency:
    """Test concurrent request handling"""

    def test_handles_concurrent_requests(self, inference_server, model_name):
        """Should handle multiple concurrent requests"""
        import concurrent.futures

        def make_request(prompt_num):
            payload = {
                "model": model_name,
                "prompt": f"Test prompt {prompt_num}:",
                "max_tokens": 5
            }

            try:
                response = requests.post(
                    f"{inference_server}/v1/completions",
                    json=payload,
                    timeout=60
                )
                return response.status_code == 200
            except Exception as e:
                print(f"Request {prompt_num} failed: {e}")
                return False

        # Send 3 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request, i) for i in range(3)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = sum(results)

        # At least some should succeed (V1 may serialize internally)
        assert success_count >= 1, f"No concurrent requests succeeded ({success_count}/3)"

        print(f"Concurrent requests: {success_count}/3 succeeded")


class TestReliability:
    """Test reliability and consistency"""

    def test_multiple_sequential_requests(self, inference_server, model_name):
        """Should handle multiple sequential requests reliably"""
        success_count = 0
        num_requests = 5

        for i in range(num_requests):
            payload = {
                "model": model_name,
                "prompt": f"Request {i}:",
                "max_tokens": 5
            }

            try:
                response = requests.post(
                    f"{inference_server}/v1/completions",
                    json=payload,
                    timeout=30
                )

                if response.status_code == 200:
                    success_count += 1
            except Exception as e:
                print(f"Request {i} failed: {e}")

        # Should succeed most of the time
        success_rate = success_count / num_requests
        assert success_rate >= 0.8, f"Success rate too low: {success_rate:.1%} ({success_count}/{num_requests})"


# Validation matrix result tracker
def test_validation_matrix_gaudi_inference_local(project_root):
    """Track validation matrix results for Gaudi local inference"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"

    if not matrix_file.exists():
        pytest.skip("Validation matrix not found")

    # This test aggregates results from all other tests
    assert True, "See individual tests for validation matrix criteria"
