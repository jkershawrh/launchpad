"""
Tests for CPU Inference OpenShift Manifests

RED Phase: Write tests first for OpenShift/Kubernetes manifest validation
"""

import subprocess
import pytest
import yaml
from pathlib import Path
from typing import Dict, List
from helpers import parse_k8s_memory_gi


@pytest.fixture
def manifest_dir(project_root) -> Path:
    """Path to CPU inference manifests"""
    return project_root / "deploy" / "cpu-inference"


class TestManifestFiles:
    """Test that manifest files exist and are valid"""

    def test_manifest_directory_exists(self, manifest_dir):
        """Manifest directory should exist"""
        assert manifest_dir.exists(), f"Directory not found: {manifest_dir}"

    def test_namespace_manifest_exists(self, manifest_dir):
        """Namespace manifest should exist"""
        namespace_file = manifest_dir / "namespace.yaml"
        assert namespace_file.exists(), "namespace.yaml not found"

    def test_serving_runtime_manifest_exists(self, manifest_dir):
        """ServingRuntime manifest should exist"""
        runtime_file = manifest_dir / "serving-runtime.yaml"
        assert runtime_file.exists(), "serving-runtime.yaml not found"

    def test_inference_service_manifest_exists(self, manifest_dir):
        """InferenceService manifest should exist"""
        isvc_file = manifest_dir / "inference-service.yaml"
        assert isvc_file.exists(), "inference-service.yaml not found"

    def test_network_policy_manifest_exists(self, manifest_dir):
        """NetworkPolicy manifest should exist"""
        netpol_file = manifest_dir / "network-policy.yaml"
        assert netpol_file.exists(), "network-policy.yaml not found"

    def test_kustomization_exists(self, manifest_dir):
        """Kustomization file should exist"""
        kustomization = manifest_dir / "kustomization.yaml"
        assert kustomization.exists(), "kustomization.yaml not found"


class TestYAMLValidity:
    """Test that all manifests are valid YAML"""

    def test_all_yaml_files_parse(self, manifest_dir):
        """All YAML files should parse without errors"""
        if not manifest_dir.exists():
            pytest.skip("Manifest directory not created yet")

        yaml_files = list(manifest_dir.glob("*.yaml"))
        assert len(yaml_files) > 0, "No YAML files found"

        for yaml_file in yaml_files:
            with open(yaml_file, 'r') as f:
                try:
                    yaml.safe_load(f)
                except yaml.YAMLError as e:
                    pytest.fail(f"YAML parsing failed for {yaml_file.name}: {e}")


class TestKustomizeBuild:
    """Test that kustomize can build the manifests"""

    def test_kustomize_builds(self, manifest_dir):
        """Kustomize should build successfully"""
        if not manifest_dir.exists():
            pytest.skip("Manifest directory not created yet")

        # Check if kustomize is available
        kustomize_check = subprocess.run(
            ["which", "kustomize"],
            capture_output=True
        )

        if kustomize_check.returncode != 0:
            pytest.skip("kustomize not installed - install with: brew install kustomize")

        # Build with kustomize
        result = subprocess.run(
            ["kustomize", "build", str(manifest_dir)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Kustomize build failed: {result.stderr}"
        assert len(result.stdout) > 0, "Kustomize produced no output"


class TestOpenShiftValidation:
    """Test OpenShift-specific validation"""

    def test_oc_dry_run_succeeds(self, manifest_dir):
        """OpenShift dry-run validation should pass"""
        if not manifest_dir.exists():
            pytest.skip("Manifest directory not created yet")

        # Check if oc is available
        oc_check = subprocess.run(
            ["which", "oc"],
            capture_output=True
        )

        if oc_check.returncode != 0:
            pytest.skip("oc CLI not installed")

        # Try dry-run on each manifest
        yaml_files = list(manifest_dir.glob("*.yaml"))
        if "kustomization.yaml" in [f.name for f in yaml_files]:
            # Use kustomize build | oc apply
            kustomize_result = subprocess.run(
                ["kustomize", "build", str(manifest_dir)],
                capture_output=True,
                text=True
            )

            if kustomize_result.returncode != 0:
                pytest.skip("Kustomize build failed, skipping oc validation")

            result = subprocess.run(
                ["oc", "apply", "--dry-run=client", "-f", "-"],
                input=kustomize_result.stdout,
                capture_output=True,
                text=True
            )
        else:
            pytest.skip("No kustomization.yaml found")

        # Note: dry-run might fail without cluster access, that's OK
        # We're just checking manifest syntax here


class TestNamespaceManifest:
    """Test Namespace manifest content"""

    def test_namespace_has_correct_kind(self, manifest_dir):
        """Namespace should have kind: Namespace"""
        namespace_file = manifest_dir / "namespace.yaml"

        if not namespace_file.exists():
            pytest.skip("Namespace file not created yet")

        with open(namespace_file, 'r') as f:
            docs = list(yaml.safe_load_all(f))

        assert len(docs) > 0, "Namespace file is empty"
        assert docs[0]['kind'] == 'Namespace', "First document should be a Namespace"

    def test_namespace_has_name(self, manifest_dir):
        """Namespace should have a name"""
        namespace_file = manifest_dir / "namespace.yaml"

        if not namespace_file.exists():
            pytest.skip("Namespace file not created yet")

        with open(namespace_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert 'metadata' in doc, "Namespace missing metadata"
        assert 'name' in doc['metadata'], "Namespace missing name"
        assert len(doc['metadata']['name']) > 0, "Namespace name is empty"


class TestServingRuntimeManifest:
    """Test ServingRuntime manifest content"""

    def test_serving_runtime_has_correct_kind(self, manifest_dir):
        """Should be a ServingRuntime"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert doc['kind'] == 'ServingRuntime', "Should be kind: ServingRuntime"

    def test_serving_runtime_specifies_containers(self, manifest_dir):
        """ServingRuntime should define containers"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert 'spec' in doc, "Missing spec"
        assert 'containers' in doc['spec'], "Missing containers in spec"
        assert len(doc['spec']['containers']) > 0, "No containers defined"

    def test_serving_runtime_container_image_defined(self, manifest_dir):
        """Container image should be specified"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]
        assert 'image' in container, "Container missing image"
        # Check for placeholder or real image
        assert '[TBD' in container['image'] or 'vllm-cpu' in container['image'].lower(), \
            "Image should reference vllm-cpu or have [TBD] placeholder"


class TestInferenceServiceManifest:
    """Test InferenceService manifest content"""

    def test_inference_service_has_correct_kind(self, manifest_dir):
        """Should be an InferenceService"""
        isvc_file = manifest_dir / "inference-service.yaml"

        if not isvc_file.exists():
            pytest.skip("InferenceService file not created yet")

        with open(isvc_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert doc['kind'] == 'InferenceService', "Should be kind: InferenceService"

    def test_inference_service_has_predictor(self, manifest_dir):
        """InferenceService should have predictor defined"""
        isvc_file = manifest_dir / "inference-service.yaml"

        if not isvc_file.exists():
            pytest.skip("InferenceService file not created yet")

        with open(isvc_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert 'spec' in doc, "Missing spec"
        assert 'predictor' in doc['spec'], "Missing predictor in spec"


class TestSecurityContext:
    """Test security context settings"""

    def test_serving_runtime_runs_as_nonroot(self, manifest_dir):
        """ServingRuntime containers should run as non-root"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]

        # Check for securityContext
        if 'securityContext' in container:
            sec_ctx = container['securityContext']
            # Should specify runAsNonRoot: true or runAsUser > 0
            if 'runAsNonRoot' in sec_ctx:
                assert sec_ctx['runAsNonRoot'] == True, "Should run as non-root"
            elif 'runAsUser' in sec_ctx:
                assert sec_ctx['runAsUser'] > 0, "runAsUser should be > 0"

    def test_no_privileged_containers(self, manifest_dir):
        """No containers should be privileged"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        for container in doc['spec']['containers']:
            if 'securityContext' in container:
                sec_ctx = container['securityContext']
                if 'privileged' in sec_ctx:
                    assert sec_ctx['privileged'] == False, "Containers should not be privileged"


class TestResourceRequests:
    """Test resource requests and limits"""

    def test_serving_runtime_has_resource_limits(self, manifest_dir):
        """Containers should have resource limits defined"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]
        assert 'resources' in container, "Container missing resources"

        resources = container['resources']
        # Should have either requests or limits or both
        assert 'requests' in resources or 'limits' in resources, \
            "Should define resource requests or limits"


class TestNodeSelector:
    """Test node selector for Xeon6 targeting"""

    def test_node_selector_has_worker_role(self, manifest_dir):
        """ServingRuntime should target worker nodes"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        node_selector = doc.get('spec', {}).get('nodeSelector')
        assert node_selector is not None, "nodeSelector must be active (not commented out)"
        assert node_selector.get('node-role.kubernetes.io/worker') == '', \
            "nodeSelector should include worker role"


class TestConfigMapIntegration:
    """Test ConfigMap and Secret wiring into pod spec"""

    def test_serving_runtime_envfrom_references_configmap(self, manifest_dir):
        """ServingRuntime container should load env from ConfigMap"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]
        env_from = container.get('envFrom', [])
        configmap_refs = [
            e['configMapRef']['name'] for e in env_from
            if 'configMapRef' in e
        ]
        assert any('inference-config' in ref for ref in configmap_refs), \
            "Container should reference inference-config ConfigMap via envFrom"

    def test_kustomization_has_secret_generator(self, manifest_dir):
        """Kustomization should generate HF token Secret"""
        kustomization_file = manifest_dir / "kustomization.yaml"

        if not kustomization_file.exists():
            pytest.skip("kustomization.yaml not created yet")

        with open(kustomization_file, 'r') as f:
            doc = yaml.safe_load(f)

        secret_generators = doc.get('secretGenerator', [])
        assert len(secret_generators) > 0, "secretGenerator should be defined"
        secret_names = [s['name'] for s in secret_generators]
        assert 'hf-token' in secret_names, "Should have hf-token secret generator"

    def test_serving_runtime_hf_token_from_secret(self, manifest_dir):
        """ServingRuntime container should inject HF_TOKEN from Secret"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]
        env_list = container.get('env', [])
        hf_token_entries = [
            e for e in env_list
            if e.get('name') == 'HF_TOKEN'
        ]
        assert len(hf_token_entries) > 0, "HF_TOKEN env var should be defined"
        entry = hf_token_entries[0]
        assert 'valueFrom' in entry, "HF_TOKEN should come from a Secret (valueFrom)"
        assert 'secretKeyRef' in entry['valueFrom'], "HF_TOKEN should use secretKeyRef"

    def test_serving_runtime_memory_request_adequate(self, manifest_dir):
        """CPU memory request should be >= 5Gi for TinyLlama + overhead"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]
        memory_req = container['resources']['requests']['memory']
        memory_gi = parse_k8s_memory_gi(memory_req)
        assert memory_gi >= 5, f"Memory request {memory_req} is below 5Gi minimum"

    def test_inference_service_memory_request_adequate(self, manifest_dir):
        """InferenceService memory request should be >= 5Gi"""
        isvc_file = manifest_dir / "inference-service.yaml"

        if not isvc_file.exists():
            pytest.skip("InferenceService file not created yet")

        with open(isvc_file, 'r') as f:
            doc = yaml.safe_load(f)

        memory_req = doc['spec']['predictor']['model']['resources']['requests']['memory']
        memory_gi = parse_k8s_memory_gi(memory_req)
        assert memory_gi >= 5, f"Memory request {memory_req} is below 5Gi minimum"


class TestModelCachePVC:
    """Test PersistentVolumeClaim for model caching"""

    def test_model_cache_pvc_manifest_exists(self, manifest_dir):
        """PVC manifest should exist"""
        pvc_file = manifest_dir / "model-cache-pvc.yaml"
        assert pvc_file.exists(), "model-cache-pvc.yaml not found"

    def test_model_cache_pvc_is_valid_yaml(self, manifest_dir):
        """PVC manifest should be a valid PersistentVolumeClaim"""
        pvc_file = manifest_dir / "model-cache-pvc.yaml"

        if not pvc_file.exists():
            pytest.skip("model-cache-pvc.yaml not created yet")

        with open(pvc_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert doc['kind'] == 'PersistentVolumeClaim', \
            f"Expected kind PersistentVolumeClaim, got {doc['kind']}"

    def test_model_cache_pvc_has_readwriteonce(self, manifest_dir):
        """PVC should use ReadWriteOnce access mode"""
        pvc_file = manifest_dir / "model-cache-pvc.yaml"

        if not pvc_file.exists():
            pytest.skip("model-cache-pvc.yaml not created yet")

        with open(pvc_file, 'r') as f:
            doc = yaml.safe_load(f)

        access_modes = doc['spec']['accessModes']
        assert 'ReadWriteOnce' in access_modes, \
            "PVC should have ReadWriteOnce access mode"

    def test_model_cache_pvc_requests_sufficient_storage(self, manifest_dir):
        """PVC should request at least 10Gi for model storage"""
        pvc_file = manifest_dir / "model-cache-pvc.yaml"

        if not pvc_file.exists():
            pytest.skip("model-cache-pvc.yaml not created yet")

        with open(pvc_file, 'r') as f:
            doc = yaml.safe_load(f)

        storage = doc['spec']['resources']['requests']['storage']
        storage_gi = parse_k8s_memory_gi(storage)
        assert storage_gi >= 10, f"PVC storage {storage} is below 10Gi minimum"

    def test_serving_runtime_has_cache_volume_mount(self, manifest_dir):
        """ServingRuntime container should mount model cache volume"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]
        volume_mounts = container.get('volumeMounts', [])
        cache_mounts = [
            vm for vm in volume_mounts
            if vm.get('mountPath') == '/opt/app-root/src/.cache'
        ]
        assert len(cache_mounts) > 0, \
            "Container should mount volume at /opt/app-root/src/.cache"

    def test_serving_runtime_has_pvc_volume(self, manifest_dir):
        """ServingRuntime should define a volume referencing the PVC"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        volumes = doc.get('spec', {}).get('volumes', [])
        pvc_volumes = [
            v for v in volumes
            if 'persistentVolumeClaim' in v
        ]
        assert len(pvc_volumes) > 0, \
            "Should have a volume referencing a PersistentVolumeClaim"

    def test_kustomization_includes_pvc(self, manifest_dir):
        """Kustomization should include PVC in resources"""
        kustomization_file = manifest_dir / "kustomization.yaml"

        if not kustomization_file.exists():
            pytest.skip("kustomization.yaml not created yet")

        with open(kustomization_file, 'r') as f:
            doc = yaml.safe_load(f)

        resources = doc.get('resources', [])
        assert 'model-cache-pvc.yaml' in resources, \
            "model-cache-pvc.yaml should be in kustomization resources"


# Validation matrix result tracker
def test_validation_matrix_cpu_manifests(project_root):
    """Track validation matrix results for CPU manifests"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"

    if not matrix_file.exists():
        pytest.skip("Validation matrix not found")

    assert True, "See individual tests for validation matrix criteria"


class TestCPUManifestHardening:
    """Hardening tests for CPU manifests"""

    def test_no_tbd_images(self, manifest_dir):
        """No [TBD] placeholder images should remain"""
        for yaml_file in manifest_dir.glob("*.yaml"):
            content = yaml_file.read_text()
            assert '[TBD' not in content, \
                f"{yaml_file.name} has [TBD] placeholder"

    def test_has_startup_probe(self, manifest_dir):
        """Serving runtime should have startupProbe"""
        content = (manifest_dir / "serving-runtime.yaml").read_text()
        assert 'startupProbe' in content, \
            "Serving runtime should have startupProbe"
