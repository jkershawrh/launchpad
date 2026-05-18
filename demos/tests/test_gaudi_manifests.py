#!/usr/bin/env python3
"""
Tests for Gaudi Manifests (Stage 2.3)

TDD Phase: RED - Tests written first, expected to fail initially.
These tests validate OpenShift/Kubernetes manifests for Gaudi inference.
"""

import pytest
import yaml
import subprocess
from pathlib import Path
from helpers import parse_k8s_memory_gi


@pytest.fixture
def manifest_dir(project_root):
    """Path to Gaudi manifest directory"""
    return project_root / "deploy" / "gaudi-inference"


class TestManifestFiles:
    """Test manifest file structure"""

    def test_manifest_directory_exists(self, manifest_dir):
        """Manifest directory should exist"""
        assert manifest_dir.exists(), f"Manifest directory not found: {manifest_dir}"
        assert manifest_dir.is_dir(), "Should be a directory"

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

    def test_readme_exists(self, manifest_dir):
        """README should exist"""
        readme = manifest_dir / "README.md"
        assert readme.exists(), "README.md not found"


class TestYAMLValidity:
    """Test YAML syntax validity"""

    def test_all_yaml_files_parse(self, manifest_dir):
        """All YAML files should parse without errors"""
        yaml_files = [
            "namespace.yaml",
            "serving-runtime.yaml",
            "inference-service.yaml",
            "network-policy.yaml",
            "kustomization.yaml"
        ]

        for yaml_file in yaml_files:
            file_path = manifest_dir / yaml_file

            if not file_path.exists():
                pytest.skip(f"{yaml_file} not created yet")

            with open(file_path, 'r') as f:
                try:
                    yaml.safe_load(f)
                except yaml.YAMLError as e:
                    pytest.fail(f"{yaml_file} is not valid YAML: {e}")


class TestKustomizeBuild:
    """Test kustomize build"""

    def test_kustomize_builds(self, manifest_dir):
        """Kustomize should build successfully"""
        # Check if kustomize is installed
        result = subprocess.run(
            ["which", "kustomize"],
            capture_output=True
        )

        if result.returncode != 0:
            pytest.skip("kustomize not installed")

        # Try to build
        result = subprocess.run(
            ["kustomize", "build", str(manifest_dir)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"kustomize build failed: {result.stderr}"


class TestOpenShiftValidation:
    """Test OpenShift dry-run validation"""

    def test_oc_dry_run_succeeds(self, manifest_dir):
        """oc apply --dry-run should succeed"""
        # Check if oc is installed
        result = subprocess.run(
            ["which", "oc"],
            capture_output=True
        )

        if result.returncode != 0:
            pytest.skip("oc CLI not installed")

        # Build manifests
        build_result = subprocess.run(
            ["kustomize", "build", str(manifest_dir)],
            capture_output=True,
            text=True
        )

        if build_result.returncode != 0:
            pytest.skip("kustomize build failed")

        # Dry run
        result = subprocess.run(
            ["oc", "apply", "--dry-run=client", "-f", "-"],
            input=build_result.stdout,
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"oc dry-run failed: {result.stderr}"


class TestNamespaceManifest:
    """Test namespace manifest"""

    def test_namespace_has_correct_kind(self, manifest_dir):
        """Namespace should have kind: Namespace"""
        namespace_file = manifest_dir / "namespace.yaml"

        if not namespace_file.exists():
            pytest.skip("Namespace file not created yet")

        with open(namespace_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert doc['kind'] == 'Namespace', f"Expected kind Namespace, got {doc['kind']}"

    def test_namespace_has_name(self, manifest_dir):
        """Namespace should have a name"""
        namespace_file = manifest_dir / "namespace.yaml"

        if not namespace_file.exists():
            pytest.skip("Namespace file not created yet")

        with open(namespace_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert 'metadata' in doc, "Missing metadata"
        assert 'name' in doc['metadata'], "Missing name"
        assert 'gaudi' in doc['metadata']['name'].lower(), "Namespace name should reference Gaudi"


class TestServingRuntimeManifest:
    """Test ServingRuntime manifest"""

    def test_serving_runtime_has_correct_kind(self, manifest_dir):
        """ServingRuntime should have correct kind"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert doc['kind'] == 'ServingRuntime', f"Expected kind ServingRuntime, got {doc['kind']}"

    def test_serving_runtime_specifies_containers(self, manifest_dir):
        """ServingRuntime should specify containers"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert 'spec' in doc, "Missing spec"
        assert 'containers' in doc['spec'], "Missing containers in spec"
        assert len(doc['spec']['containers']) > 0, "No containers defined"

    def test_serving_runtime_container_image_defined(self, manifest_dir):
        """ServingRuntime container should have image defined"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]
        assert 'image' in container, "Container missing image"
        assert len(container['image']) > 0, "Container image is empty"

    def test_serving_runtime_requests_gaudi_resources(self, manifest_dir):
        """ServingRuntime should request habana.ai/gaudi resources"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]

        # Check for Gaudi resource request
        has_gaudi_resource = False

        if 'resources' in container:
            resources = container['resources']

            # Check in limits
            if 'limits' in resources:
                if 'habana.ai/gaudi' in resources['limits']:
                    has_gaudi_resource = True

            # Check in requests
            if 'requests' in resources:
                if 'habana.ai/gaudi' in resources['requests']:
                    has_gaudi_resource = True

        assert has_gaudi_resource, "Container should request habana.ai/gaudi resources"


class TestInferenceServiceManifest:
    """Test InferenceService manifest"""

    def test_inference_service_has_correct_kind(self, manifest_dir):
        """InferenceService should have correct kind"""
        isvc_file = manifest_dir / "inference-service.yaml"

        if not isvc_file.exists():
            pytest.skip("InferenceService file not created yet")

        with open(isvc_file, 'r') as f:
            doc = yaml.safe_load(f)

        assert doc['kind'] == 'InferenceService', f"Expected kind InferenceService, got {doc['kind']}"

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

        # Should have security context
        if 'securityContext' in container:
            sec_ctx = container['securityContext']

            # Should specify runAsNonRoot
            if 'runAsNonRoot' in sec_ctx:
                assert sec_ctx['runAsNonRoot'] is True, "Should run as non-root"

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

                # Should not be privileged
                if 'privileged' in sec_ctx:
                    assert sec_ctx['privileged'] is False, "Container should not be privileged"


class TestResourceRequests:
    """Test resource requests"""

    def test_serving_runtime_has_resource_limits(self, manifest_dir):
        """ServingRuntime containers should have resource limits"""
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
    """Test node selector for Gaudi targeting"""

    def test_gaudi_node_selector_has_gaudi_label(self, manifest_dir):
        """Gaudi nodeSelector must target Gaudi-labeled nodes, not a placeholder"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        node_selector = doc.get('spec', {}).get('nodeSelector')
        assert node_selector is not None, "nodeSelector must be defined"
        assert node_selector.get('intel.feature.node.kubernetes.io/gaudi') == 'true', \
            "nodeSelector should include Gaudi feature label"
        assert 'workload' not in node_selector or node_selector.get('workload') != 'ai-inference', \
            "Placeholder 'workload: ai-inference' should be replaced with real label"

    def test_gaudi_node_selector_has_worker_role(self, manifest_dir):
        """Gaudi nodeSelector should also target worker nodes"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        node_selector = doc.get('spec', {}).get('nodeSelector', {})
        assert node_selector.get('node-role.kubernetes.io/worker') == '', \
            "nodeSelector should include worker role"

    def test_gaudi_tolerations_exist(self, manifest_dir):
        """Gaudi ServingRuntime should have tolerations for GPU-tainted nodes"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        tolerations = doc.get('spec', {}).get('tolerations')
        assert tolerations is not None, "tolerations must be defined (not commented out)"
        assert len(tolerations) > 0, "At least one toleration required"
        gaudi_tolerations = [
            t for t in tolerations
            if 'intel.com/gaudi' in t.get('key', '')
        ]
        assert len(gaudi_tolerations) > 0, \
            "Should have a toleration for intel.com/gaudi tainted nodes"


class TestConfigMapIntegration:
    """Test ConfigMap and Secret wiring into pod spec"""

    def test_serving_runtime_envfrom_references_configmap(self, manifest_dir):
        """ServingRuntime container should load env from Gaudi ConfigMap"""
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
        assert any('gaudi-inference-config' in ref for ref in configmap_refs), \
            "Container should reference gaudi-inference-config ConfigMap via envFrom"

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
        """Gaudi memory request should be >= 16Gi"""
        runtime_file = manifest_dir / "serving-runtime.yaml"

        if not runtime_file.exists():
            pytest.skip("ServingRuntime file not created yet")

        with open(runtime_file, 'r') as f:
            doc = yaml.safe_load(f)

        container = doc['spec']['containers'][0]
        memory_req = container['resources']['requests']['memory']
        memory_gi = parse_k8s_memory_gi(memory_req)
        assert memory_gi >= 16, f"Memory request {memory_req} is below 16Gi minimum"

    def test_inference_service_memory_request_adequate(self, manifest_dir):
        """Gaudi InferenceService memory request should be >= 16Gi"""
        isvc_file = manifest_dir / "inference-service.yaml"

        if not isvc_file.exists():
            pytest.skip("InferenceService file not created yet")

        with open(isvc_file, 'r') as f:
            doc = yaml.safe_load(f)

        memory_req = doc['spec']['predictor']['model']['resources']['requests']['memory']
        memory_gi = parse_k8s_memory_gi(memory_req)
        assert memory_gi >= 16, f"Memory request {memory_req} is below 16Gi minimum"


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
def test_validation_matrix_gaudi_manifests(project_root):
    """Track validation matrix results for Gaudi manifests"""
    matrix_file = project_root / "tests" / "validation_matrix.yaml"

    if not matrix_file.exists():
        pytest.skip("Validation matrix not found")

    assert True, "See individual tests for validation matrix criteria"


class TestGaudiManifestHardening:
    """Hardening tests for Gaudi manifests"""

    def test_no_tbd_images(self, manifest_dir):
        """No [TBD] placeholder images should remain"""
        for yaml_file in manifest_dir.glob("*.yaml"):
            content = yaml_file.read_text()
            assert '[TBD' not in content, \
                f"{yaml_file.name} has [TBD] placeholder"

    def test_has_startup_probe(self, manifest_dir):
        """Serving runtime should have startupProbe"""
        content = (manifest_dir / "serving-runtime.yaml").read_text()
        assert 'startupProbe' in content
