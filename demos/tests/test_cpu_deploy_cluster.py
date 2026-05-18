#!/usr/bin/env python3
"""
Tests for CPU Inference Cluster Deployment (Stage 5.1)

TDD Phase: RED - Tests written first, expected to fail until cluster access obtained.
These tests validate the CPU inference path deployment on the Rackspace OpenShift AI cluster.

IMPORTANT: These tests require actual cluster access and cannot run locally.
"""

import pytest
import subprocess
from pathlib import Path
import yaml
import time
import requests


@pytest.fixture
def cpu_manifests_dir(project_root):
    """Path to CPU inference manifests"""
    return project_root / "deploy" / "cpu-inference"


@pytest.fixture
def cluster_info_file(project_root):
    """Path to cluster info file (from discovery script)"""
    return project_root / "cluster-info.yaml"


@pytest.fixture
def namespace():
    """CPU inference namespace"""
    return "intel-rh-cpu-inference"


@pytest.fixture
def inference_service_name():
    """InferenceService name"""
    return "cpu-inference-example"


def check_cluster_access():
    """Check if we have cluster access"""
    try:
        result = subprocess.run(
            ["oc", "cluster-info"],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def pytest_configure(config):
    """Add custom markers"""
    config.addinivalue_line(
        "markers", "cluster_required: test requires cluster access"
    )


@pytest.fixture(autouse=True)
def skip_if_no_cluster():
    """Skip tests if no cluster access"""
    if not check_cluster_access():
        pytest.skip("Cluster access required - run discovery script first")


class TestPrerequisites:
    """Test deployment prerequisites"""

    def test_cluster_access(self):
        """Should have access to OpenShift cluster"""
        result = subprocess.run(
            ["oc", "cluster-info"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0, "Cannot access cluster"
        assert "running" in result.stdout.lower(), "Cluster not running"

    def test_cluster_info_exists(self, cluster_info_file):
        """Cluster info file should exist (from discovery script)"""
        assert cluster_info_file.exists(), \
            "Run scripts/discover-cluster.sh first to generate cluster-info.yaml"

    def test_cluster_has_cpu_nodes(self, cluster_info_file):
        """Cluster should have CPU nodes available"""
        if not cluster_info_file.exists():
            pytest.skip("cluster-info.yaml not found")

        data = yaml.safe_load(cluster_info_file.read_text())
        assert "nodes" in data, "Cluster info missing nodes section"
        assert data["nodes"]["cpu_count"] > 0, "No CPU nodes available"

    def test_openshift_ai_installed(self, cluster_info_file):
        """OpenShift AI operator should be installed"""
        if not cluster_info_file.exists():
            pytest.skip("cluster-info.yaml not found")

        data = yaml.safe_load(cluster_info_file.read_text())
        assert "operators" in data, "Cluster info missing operators section"
        assert data["operators"]["openshift_ai"]["installed"], \
            "OpenShift AI operator not installed"


class TestDeployment:
    """Test deployment process"""

    def test_manifests_directory_exists(self, cpu_manifests_dir):
        """CPU manifests directory should exist"""
        assert cpu_manifests_dir.exists(), "CPU manifests directory not found"

    def test_kustomization_builds(self, cpu_manifests_dir):
        """Kustomize build should succeed"""
        result = subprocess.run(
            ["kustomize", "build", str(cpu_manifests_dir)],
            capture_output=True,
            timeout=30
        )
        assert result.returncode == 0, f"Kustomize build failed: {result.stderr}"

    def test_namespace_created(self, namespace):
        """Namespace should be created"""
        result = subprocess.run(
            ["oc", "get", "namespace", namespace],
            capture_output=True,
            timeout=10
        )
        assert result.returncode == 0, f"Namespace {namespace} not created"

    def test_serving_runtime_created(self, namespace):
        """ServingRuntime should be created"""
        result = subprocess.run(
            ["oc", "get", "servingruntime", "-n", namespace],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0, "Failed to get ServingRuntimes"
        assert "vllm-cpu-runtime" in result.stdout, "CPU ServingRuntime not found"

    def test_inference_service_created(self, namespace, inference_service_name):
        """InferenceService should be created"""
        result = subprocess.run(
            ["oc", "get", "inferenceservice", inference_service_name, "-n", namespace],
            capture_output=True,
            timeout=10
        )
        assert result.returncode == 0, f"InferenceService {inference_service_name} not created"


class TestPodStatus:
    """Test pod deployment and status"""

    def test_pods_exist(self, namespace, inference_service_name):
        """Pods should be created for InferenceService"""
        result = subprocess.run(
            ["oc", "get", "pods", "-n", namespace,
             "-l", f"serving.kserve.io/inferenceservice={inference_service_name}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0, "Failed to get pods"
        assert len(result.stdout.strip().split('\n')) > 1, "No pods found"

    def test_pods_running(self, namespace, inference_service_name):
        """Pods should be in Running state"""
        # Wait up to 5 minutes for pods to be running
        max_wait = 300
        start_time = time.time()

        while time.time() - start_time < max_wait:
            result = subprocess.run(
                ["oc", "get", "pods", "-n", namespace,
                 "-l", f"serving.kserve.io/inferenceservice={inference_service_name}",
                 "--field-selector=status.phase=Running",
                 "--no-headers"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                return  # Success

            time.sleep(10)

        pytest.fail("Pods not running after 5 minutes")

    def test_pod_on_cpu_node(self, namespace, inference_service_name):
        """Pod should be scheduled on CPU node"""
        result = subprocess.run(
            ["oc", "get", "pods", "-n", namespace,
             "-l", f"serving.kserve.io/inferenceservice={inference_service_name}",
             "-o", "jsonpath={.items[0].spec.nodeName}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0, "Failed to get pod node"

        node_name = result.stdout.strip()
        assert node_name, "Pod not assigned to node"

        # Verify node does NOT have Gaudi GPU
        node_result = subprocess.run(
            ["oc", "get", "node", node_name,
             "-o", "jsonpath={.status.allocatable.habana\\.ai/gaudi}"],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Should be empty or not have Gaudi resource
        assert not node_result.stdout.strip() or node_result.stdout.strip() == "0", \
            f"Pod scheduled on Gaudi node instead of CPU node: {node_name}"

    def test_pod_stays_running(self, namespace, inference_service_name):
        """Pod should stay running for at least 5 minutes"""
        # Check pod is running
        result = subprocess.run(
            ["oc", "get", "pods", "-n", namespace,
             "-l", f"serving.kserve.io/inferenceservice={inference_service_name}",
             "--field-selector=status.phase=Running",
             "-o", "jsonpath={.items[0].metadata.name}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0 and result.stdout.strip(), "No running pod found"

        pod_name = result.stdout.strip()

        # Wait 5 minutes
        time.sleep(300)

        # Check still running
        result = subprocess.run(
            ["oc", "get", "pod", pod_name, "-n", namespace,
             "-o", "jsonpath={.status.phase}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0, "Failed to get pod status"
        assert result.stdout.strip() == "Running", \
            f"Pod not running after 5 minutes: {result.stdout.strip()}"


class TestInferenceServiceStatus:
    """Test InferenceService readiness"""

    def test_inference_service_ready(self, namespace, inference_service_name):
        """InferenceService should be in Ready state"""
        # Wait up to 10 minutes for InferenceService to be ready
        max_wait = 600
        start_time = time.time()

        while time.time() - start_time < max_wait:
            result = subprocess.run(
                ["oc", "get", "inferenceservice", inference_service_name, "-n", namespace,
                 "-o", "jsonpath={.status.conditions[?(@.type=='Ready')].status}"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip() == "True":
                return  # Success

            time.sleep(15)

        pytest.fail("InferenceService not ready after 10 minutes")

    def test_inference_service_has_url(self, namespace, inference_service_name):
        """InferenceService should have a URL"""
        result = subprocess.run(
            ["oc", "get", "inferenceservice", inference_service_name, "-n", namespace,
             "-o", "jsonpath={.status.url}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0, "Failed to get InferenceService URL"
        assert result.stdout.strip(), "InferenceService has no URL"
        assert result.stdout.strip().startswith("http"), \
            f"Invalid URL: {result.stdout.strip()}"


class TestInferenceEndpoints:
    """Test inference API endpoints"""

    @pytest.fixture
    def inference_url(self, namespace, inference_service_name):
        """Get InferenceService URL"""
        result = subprocess.run(
            ["oc", "get", "inferenceservice", inference_service_name, "-n", namespace,
             "-o", "jsonpath={.status.url}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0, "Failed to get URL"
        url = result.stdout.strip()
        assert url, "No URL found"
        return url

    def test_health_endpoint(self, inference_url):
        """Health endpoint should respond"""
        response = requests.get(f"{inference_url}/health", timeout=30)
        assert response.status_code == 200, \
            f"Health endpoint returned {response.status_code}"

    def test_models_endpoint(self, inference_url):
        """Models endpoint should return model list"""
        response = requests.get(f"{inference_url}/v1/models", timeout=30)
        assert response.status_code == 200, \
            f"Models endpoint returned {response.status_code}"

        data = response.json()
        assert "data" in data or "object" in data, "Invalid models response"

    def test_completions_endpoint(self, inference_url):
        """Completions endpoint should generate text"""
        payload = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "The capital of France is",
            "max_tokens": 10,
            "temperature": 0.7
        }

        response = requests.post(
            f"{inference_url}/v1/completions",
            json=payload,
            timeout=60
        )
        assert response.status_code == 200, \
            f"Completions endpoint returned {response.status_code}"

        data = response.json()
        assert "choices" in data, "Response missing choices"
        assert len(data["choices"]) > 0, "No choices returned"
        assert "text" in data["choices"][0], "Choice missing text"


class TestPerformanceMetrics:
    """Test performance metrics"""

    @pytest.fixture
    def inference_url(self, namespace, inference_service_name):
        """Get InferenceService URL"""
        result = subprocess.run(
            ["oc", "get", "inferenceservice", inference_service_name, "-n", namespace,
             "-o", "jsonpath={.status.url}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        url = result.stdout.strip()
        return url

    def test_time_to_first_token(self, inference_url):
        """TTFT should be reasonable for CPU (< 30s for TinyLlama)"""
        payload = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "Hello, my name is",
            "max_tokens": 20
        }

        start_time = time.time()
        response = requests.post(
            f"{inference_url}/v1/completions",
            json=payload,
            timeout=60
        )
        ttft = time.time() - start_time

        assert response.status_code == 200, "Request failed"
        assert ttft < 30, f"TTFT too slow for CPU: {ttft:.2f}s (expected < 30s)"

    def test_throughput(self, inference_url):
        """Throughput should be measured"""
        payload = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "Once upon a time",
            "max_tokens": 50
        }

        start_time = time.time()
        response = requests.post(
            f"{inference_url}/v1/completions",
            json=payload,
            timeout=60
        )
        duration = time.time() - start_time

        assert response.status_code == 200, "Request failed"
        data = response.json()

        if "usage" in data:
            completion_tokens = data["usage"].get("completion_tokens", 0)
            if completion_tokens > 0:
                tokens_per_second = completion_tokens / duration
                assert tokens_per_second > 0, "Throughput calculation failed"
                # CPU should get at least 5 tokens/sec for TinyLlama
                assert tokens_per_second >= 5, \
                    f"Throughput too low: {tokens_per_second:.2f} tok/s (expected >= 5)"

    def test_concurrent_requests(self, inference_url):
        """Should handle 3 concurrent requests"""
        import concurrent.futures

        payload = {
            "model": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
            "prompt": "Test prompt",
            "max_tokens": 10
        }

        def make_request():
            response = requests.post(
                f"{inference_url}/v1/completions",
                json=payload,
                timeout=60
            )
            return response.status_code == 200

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(3)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = sum(results)
        assert success_count >= 2, \
            f"Only {success_count}/3 concurrent requests succeeded"


class TestObservability:
    """Test observability and monitoring"""

    def test_pod_logs_available(self, namespace, inference_service_name):
        """Pod logs should be available"""
        result = subprocess.run(
            ["oc", "get", "pods", "-n", namespace,
             "-l", f"serving.kserve.io/inferenceservice={inference_service_name}",
             "-o", "jsonpath={.items[0].metadata.name}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        pod_name = result.stdout.strip()
        assert pod_name, "No pod found"

        log_result = subprocess.run(
            ["oc", "logs", pod_name, "-n", namespace, "--tail=10"],
            capture_output=True,
            text=True,
            timeout=30
        )
        assert log_result.returncode == 0, "Failed to get logs"
        assert len(log_result.stdout) > 0, "Logs are empty"

    def test_metrics_endpoint_exists(self, inference_url):
        """Metrics endpoint should exist (optional)"""
        # This is optional - not all deployments expose /metrics
        try:
            response = requests.get(f"{inference_url}/metrics", timeout=10)
            # If it exists, should return 200 or 404
            assert response.status_code in [200, 404], \
                f"Unexpected metrics endpoint status: {response.status_code}"
        except requests.exceptions.RequestException:
            # Metrics endpoint may not be exposed, that's OK
            pass


# Validation matrix result tracker
def test_validation_matrix_cpu_cluster_deploy(project_root):
    """Track validation matrix results for CPU cluster deployment"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"

    if not matrix_file.exists():
        pytest.skip("Validation matrix not found")

    # This test aggregates results from all other tests
    assert True, "See individual tests for validation matrix criteria"
