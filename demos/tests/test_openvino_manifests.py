#!/usr/bin/env python3
"""
Tests for OpenVINO CPU Inference Manifests

TDD Phase: RED - Tests written first.
OpenVINO Model Server is a built-in OpenShift AI runtime.
These manifests deploy InferenceServices for embeddings,
classification, and reranking on Xeon 6.
"""

import pytest
import yaml
from pathlib import Path
from conftest import parse_k8s_memory_gi


@pytest.fixture
def manifest_dir(project_root) -> Path:
    return project_root / "deploy" / "openvino-cpu"


class TestManifestFiles:
    """Test manifest file structure"""

    def test_manifest_directory_exists(self, manifest_dir):
        """OpenVINO manifest directory should exist"""
        assert manifest_dir.exists(), "deploy/openvino-cpu/ not found"

    def test_kustomization_exists(self, manifest_dir):
        """Kustomization file should exist"""
        assert (manifest_dir / "kustomization.yaml").exists()

    def test_namespace_exists(self, manifest_dir):
        """Namespace manifest should exist"""
        assert (manifest_dir / "namespace.yaml").exists()

    def test_serving_runtime_exists(self, manifest_dir):
        """ServingRuntime manifest should exist"""
        assert (manifest_dir / "serving-runtime.yaml").exists()

    def test_inference_service_exists(self, manifest_dir):
        """At least one InferenceService manifest should exist"""
        isvc_files = list(manifest_dir.glob("inference-service*.yaml"))
        assert len(isvc_files) > 0, "No InferenceService manifests found"


class TestServingRuntime:
    """Test OpenVINO ServingRuntime"""

    def test_runtime_uses_openvino(self, manifest_dir):
        """ServingRuntime should reference OpenVINO"""
        runtime_file = manifest_dir / "serving-runtime.yaml"
        if not runtime_file.exists():
            pytest.skip("serving-runtime.yaml not created yet")
        with open(runtime_file) as f:
            doc = yaml.safe_load(f)
        content = yaml.dump(doc).lower()
        assert 'openvino' in content, "ServingRuntime should reference OpenVINO"

    def test_runtime_supports_onnx(self, manifest_dir):
        """ServingRuntime should support ONNX model format"""
        runtime_file = manifest_dir / "serving-runtime.yaml"
        if not runtime_file.exists():
            pytest.skip("serving-runtime.yaml not created yet")
        with open(runtime_file) as f:
            doc = yaml.safe_load(f)
        formats = [f['name'] for f in doc['spec'].get('supportedModelFormats', [])]
        assert 'onnx' in formats or 'openvino_ir' in formats, \
            "Should support ONNX or OpenVINO IR format"

    def test_runtime_targets_cpu(self, manifest_dir):
        """ServingRuntime should target CPU device"""
        runtime_file = manifest_dir / "serving-runtime.yaml"
        if not runtime_file.exists():
            pytest.skip("serving-runtime.yaml not created yet")
        content = runtime_file.read_text()
        assert 'CPU' in content or 'cpu' in content, \
            "Should target CPU device"

    def test_runtime_has_bf16_hint(self, manifest_dir):
        """ServingRuntime should enable BF16 for AMX acceleration"""
        runtime_file = manifest_dir / "serving-runtime.yaml"
        if not runtime_file.exists():
            pytest.skip("serving-runtime.yaml not created yet")
        content = runtime_file.read_text()
        assert 'BF16' in content or 'INFERENCE_PRECISION_HINT' in content, \
            "Should have BF16 precision hint for AMX acceleration"


class TestInferenceService:
    """Test OpenVINO InferenceService(s)"""

    def test_inference_service_valid_yaml(self, manifest_dir):
        """InferenceService manifests should be valid YAML"""
        for isvc_file in manifest_dir.glob("inference-service*.yaml"):
            with open(isvc_file) as f:
                doc = yaml.safe_load(f)
            assert doc['kind'] == 'InferenceService', \
                f"{isvc_file.name} should be an InferenceService"

    def test_inference_service_has_predictor(self, manifest_dir):
        """InferenceService should have predictor spec"""
        for isvc_file in manifest_dir.glob("inference-service*.yaml"):
            with open(isvc_file) as f:
                doc = yaml.safe_load(f)
            assert 'predictor' in doc.get('spec', {}), \
                f"{isvc_file.name} missing predictor"


class TestKustomization:
    """Test kustomization.yaml"""

    def test_kustomization_includes_all_resources(self, manifest_dir):
        """Kustomization should list all manifest files"""
        kust_file = manifest_dir / "kustomization.yaml"
        if not kust_file.exists():
            pytest.skip("kustomization.yaml not created yet")
        with open(kust_file) as f:
            doc = yaml.safe_load(f)
        resources = doc.get('resources', [])
        assert 'namespace.yaml' in resources
        assert 'serving-runtime.yaml' in resources


class TestModelExportScript:
    """Test model export script for OpenVINO"""

    def test_export_script_exists(self, project_root):
        """Model export script should exist"""
        script = project_root / "scripts" / "export-models.sh"
        assert script.exists(), "scripts/export-models.sh not found"

    def test_export_script_is_executable(self, project_root):
        """Export script should be executable"""
        script = project_root / "scripts" / "export-models.sh"
        if not script.exists():
            pytest.skip("export-models.sh not created yet")
        import os
        assert os.access(script, os.X_OK)

    def test_export_script_supports_help(self, project_root):
        """Export script should have --help"""
        import subprocess
        script = project_root / "scripts" / "export-models.sh"
        if not script.exists():
            pytest.skip("export-models.sh not created yet")
        result = subprocess.run(
            [str(script), "--help"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        output = (result.stdout + result.stderr).lower()
        assert 'openvino' in output or 'onnx' in output or 'export' in output

    def test_export_script_references_embedding_model(self, project_root):
        """Export script should reference an embedding model"""
        script = project_root / "scripts" / "export-models.sh"
        if not script.exists():
            pytest.skip("export-models.sh not created yet")
        content = script.read_text()
        assert 'MiniLM' in content or 'minilm' in content or 'embeddings' in content.lower(), \
            "Should reference an embedding model for export"
