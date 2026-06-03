"""
TDD: Workload classification — classify catalog items by computational profile,
match to hardware, right-size quotas.
"""
import os
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("INTEGRATION_API_KEY", "test-integration-key")

from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem, LabRequest
from app.domain.workload import HardwareMatch, WorkloadProfile, WorkloadType


def _catalog_item(item_id="test-item", **overrides):
    defaults = dict(
        catalog_item_id=item_id,
        display_name="Test Item",
        description="Test catalog item",
        category=CatalogCategory.QUICK_START,
        status=CatalogStatus.ACTIVE,
    )
    defaults.update(overrides)
    return CatalogItem(**defaults)


def _request(**overrides):
    defaults = dict(
        tenant_id="test",
        requester_id="user-1",
        catalog_item_id="test-item",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(overrides)
    return LabRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Domain Models
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkloadModels:

    def test_workload_type_values(self):
        assert WorkloadType.CPU_INFERENCE == "cpu_inference"
        assert WorkloadType.GPU_INFERENCE == "gpu_inference"
        assert WorkloadType.TRAINING == "training"
        assert WorkloadType.RAG_PIPELINE == "rag_pipeline"
        assert WorkloadType.AGENT == "agent"

    def test_workload_profile_defaults(self):
        profile = WorkloadProfile(workload_type=WorkloadType.CPU_INFERENCE)
        assert profile.compute_intensity == "medium"
        assert profile.gpu_required is False
        assert profile.confidence == 0.5

    def test_workload_profile_gpu_required(self):
        profile = WorkloadProfile(
            workload_type=WorkloadType.GPU_INFERENCE,
            gpu_required=True,
            gpu_mode="endpoint",
            compute_intensity="high",
        )
        assert profile.gpu_required is True
        assert profile.gpu_mode == "endpoint"

    def test_hardware_match_with_reasons(self):
        match = HardwareMatch(
            hardware_profile="gaudi-endpoint",
            score=85.0,
            reasons=["GPU required for inference", "high compute intensity"],
            right_sized_quota="standard",
        )
        assert match.score == 85.0
        assert len(match.reasons) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# WorkloadClassifier — Classification from catalog metadata
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifyFromMetadata:

    def test_importable(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()
        assert clf is not None

    def test_cpu_only_item_classified_as_cpu_inference(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(
            metadata={"cpu_only": True},
            default_hardware_profile="xeon-basic",
        )
        profile = clf.classify(item, _request())
        assert profile.workload_type == WorkloadType.CPU_INFERENCE
        assert profile.gpu_required is False
        assert profile.confidence >= 0.8

    def test_gaudi_direct_capability_classified_as_training(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(
            required_capabilities=["openshift", "gaudi_direct"],
            default_hardware_profile="gaudi-direct",
        )
        profile = clf.classify(item, _request())
        assert profile.workload_type == WorkloadType.TRAINING
        assert profile.gpu_required is True
        assert profile.gpu_mode == "direct"

    def test_vector_db_capability_classified_as_rag(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(
            required_capabilities=["openshift", "model_endpoint", "vector_db"],
            default_hardware_profile="gaudi-endpoint",
        )
        profile = clf.classify(item, _request())
        assert profile.workload_type == WorkloadType.RAG_PIPELINE

    def test_model_endpoint_only_classified_as_gpu_inference(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(
            required_capabilities=["openshift", "model_endpoint"],
            default_hardware_profile="gaudi-endpoint",
        )
        profile = clf.classify(item, _request())
        assert profile.workload_type == WorkloadType.GPU_INFERENCE
        assert profile.gpu_required is True

    def test_minimal_item_classified_as_lightweight(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(
            required_capabilities=["openshift"],
            default_hardware_profile="xeon-basic",
            default_quota_profile="small",
        )
        profile = clf.classify(item, _request())
        assert profile.workload_type == WorkloadType.LIGHTWEIGHT

    def test_mixed_overdrive_classified_as_mixed(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(
            required_capabilities=["openshift", "model_endpoint", "gaudi_direct", "kafka"],
            default_hardware_profile="mixed-overdrive",
            default_quota_profile="large",
        )
        profile = clf.classify(item, _request())
        assert profile.workload_type == WorkloadType.MIXED


# ═══════════════════════════════════════════════════════════════════════════════
# WorkloadClassifier — Classification from hardware profile hints
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifyFromHardwareHints:

    def test_gaudi_endpoint_hw_implies_gpu_inference(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(default_hardware_profile="gaudi-endpoint")
        profile = clf.classify(item, _request())
        assert profile.gpu_required is True
        assert profile.gpu_mode == "endpoint"

    def test_gaudi_direct_hw_implies_training(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(
            default_hardware_profile="gaudi-direct",
            required_capabilities=["openshift", "gaudi_direct"],
        )
        profile = clf.classify(item, _request())
        assert profile.workload_type == WorkloadType.TRAINING

    def test_xeon_basic_hw_no_gpu(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        item = _catalog_item(default_hardware_profile="xeon-basic")
        profile = clf.classify(item, _request())
        assert profile.gpu_required is False


# ═══════════════════════════════════════════════════════════════════════════════
# WorkloadClassifier — Hardware matching
# ═══════════════════════════════════════════════════════════════════════════════


class TestHardwareMatching:

    def test_gpu_inference_prefers_gaudi_endpoint(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.GPU_INFERENCE,
            gpu_required=True,
            gpu_mode="endpoint",
            compute_intensity="high",
        )
        matches = clf.match_hardware(profile)
        assert len(matches) > 0
        assert matches[0].hardware_profile == "gaudi-endpoint"

    def test_training_prefers_gaudi_direct(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.TRAINING,
            gpu_required=True,
            gpu_mode="direct",
            compute_intensity="high",
        )
        matches = clf.match_hardware(profile)
        assert len(matches) > 0
        assert matches[0].hardware_profile == "gaudi-direct"

    def test_cpu_inference_prefers_xeon(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.CPU_INFERENCE,
            gpu_required=False,
            compute_intensity="medium",
        )
        matches = clf.match_hardware(profile)
        assert len(matches) > 0
        assert matches[0].hardware_profile in ("xeon-basic", "xeon6")

    def test_lightweight_prefers_xeon_basic(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.LIGHTWEIGHT,
            gpu_required=False,
            compute_intensity="low",
        )
        matches = clf.match_hardware(profile)
        assert len(matches) > 0
        assert matches[0].hardware_profile == "xeon-basic"

    def test_mixed_prefers_mixed_overdrive(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.MIXED,
            gpu_required=True,
            compute_intensity="high",
        )
        matches = clf.match_hardware(profile)
        assert len(matches) > 0
        assert matches[0].hardware_profile == "mixed-overdrive"

    def test_match_returns_multiple_options(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.GPU_INFERENCE,
            gpu_required=True,
        )
        matches = clf.match_hardware(profile)
        assert len(matches) >= 2

    def test_matches_sorted_by_score_descending(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.GPU_INFERENCE,
            gpu_required=True,
        )
        matches = clf.match_hardware(profile)
        scores = [m.score for m in matches]
        assert scores == sorted(scores, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# WorkloadClassifier — Right-sizing quota
# ═══════════════════════════════════════════════════════════════════════════════


class TestRightSizeQuota:

    def test_high_intensity_gpu_gets_large(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.TRAINING,
            gpu_required=True,
            compute_intensity="high",
            memory_intensity="high",
        )
        item = _catalog_item()
        quota = clf.right_size_quota(profile, item)
        assert quota == "large"

    def test_medium_intensity_gets_standard(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.GPU_INFERENCE,
            compute_intensity="medium",
            memory_intensity="medium",
        )
        item = _catalog_item()
        quota = clf.right_size_quota(profile, item)
        assert quota == "standard"

    def test_lightweight_gets_small(self):
        from app.services.workload_classifier import WorkloadClassifier
        clf = WorkloadClassifier()

        profile = WorkloadProfile(
            workload_type=WorkloadType.LIGHTWEIGHT,
            compute_intensity="low",
            memory_intensity="low",
        )
        item = _catalog_item()
        quota = clf.right_size_quota(profile, item)
        assert quota == "small"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration with ProvisioningService
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifierIntegration:

    def test_provisioning_uses_classifier(self):
        from app.services.provisioning import ProvisioningService
        from app.services.workload_classifier import WorkloadClassifier

        clf = WorkloadClassifier()
        svc = ProvisioningService(workload_classifier=clf)

        req = LabRequest(
            tenant_id="test",
            requester_id="user-1",
            catalog_item_id="inference-overdrive-quickstart",
            requested_mode=CatalogCategory.QUICK_START,
        )
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        assert session is not None

    def test_provisioning_works_without_classifier(self):
        from app.services.provisioning import ProvisioningService

        svc = ProvisioningService()
        req = LabRequest(
            tenant_id="test",
            requester_id="user-1",
            catalog_item_id="inference-overdrive-quickstart",
            requested_mode=CatalogCategory.QUICK_START,
        )
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        assert session is not None

    def test_user_override_bypasses_classifier(self):
        from app.services.provisioning import ProvisioningService
        from app.services.workload_classifier import WorkloadClassifier

        clf = WorkloadClassifier()
        svc = ProvisioningService(workload_classifier=clf)

        req = LabRequest(
            tenant_id="test",
            requester_id="user-1",
            catalog_item_id="inference-overdrive-quickstart",
            requested_mode=CatalogCategory.QUICK_START,
            hardware_profile="xeon-basic",
            quota_profile="small",
        )
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        assert session is not None

    def test_provisioning_degrades_when_classifier_raises(self):
        from app.services.provisioning import ProvisioningService

        class FailingClassifier:
            def classify(self, *a, **kw):
                raise RuntimeError("LLM exploded")

        svc = ProvisioningService(workload_classifier=FailingClassifier())
        req = LabRequest(
            tenant_id="test",
            requester_id="user-1",
            catalog_item_id="inference-overdrive-quickstart",
            requested_mode=CatalogCategory.QUICK_START,
        )
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        assert session is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Seed catalog coverage
# ═══════════════════════════════════════════════════════════════════════════════


class TestSeedCatalogClassification:

    def test_all_seed_items_classify_without_error(self):
        from app.adapters.mock.catalog import MockCatalogAdapter
        from app.services.workload_classifier import WorkloadClassifier

        clf = WorkloadClassifier()
        catalog = MockCatalogAdapter()

        for item in catalog.list_items():
            profile = clf.classify(item, _request(catalog_item_id=item.catalog_item_id))
            assert isinstance(profile, WorkloadProfile)
            assert profile.workload_type in WorkloadType
            assert 0.0 <= profile.confidence <= 1.0

    def test_training_demo_classified_as_training(self):
        from app.adapters.mock.catalog import MockCatalogAdapter
        from app.services.workload_classifier import WorkloadClassifier

        clf = WorkloadClassifier()
        catalog = MockCatalogAdapter()
        item = catalog.get_item("training-demo")
        assert item is not None

        profile = clf.classify(item, _request(catalog_item_id="training-demo"))
        assert profile.workload_type == WorkloadType.TRAINING

    def test_qs_llm_cpu_serving_classified_as_cpu_inference(self):
        from app.adapters.mock.catalog import MockCatalogAdapter
        from app.services.workload_classifier import WorkloadClassifier

        clf = WorkloadClassifier()
        catalog = MockCatalogAdapter()
        item = catalog.get_item("qs-llm-cpu-serving")
        assert item is not None

        profile = clf.classify(item, _request(catalog_item_id="qs-llm-cpu-serving"))
        assert profile.workload_type == WorkloadType.CPU_INFERENCE

    def test_enterprise_rag_classified_as_rag_pipeline(self):
        from app.adapters.mock.catalog import MockCatalogAdapter
        from app.services.workload_classifier import WorkloadClassifier

        clf = WorkloadClassifier()
        catalog = MockCatalogAdapter()
        item = catalog.get_item("enterprise-rag")
        assert item is not None

        profile = clf.classify(item, _request(catalog_item_id="enterprise-rag"))
        assert profile.workload_type == WorkloadType.RAG_PIPELINE

    def test_sandbox_minimal_classified_as_lightweight(self):
        from app.adapters.mock.catalog import MockCatalogAdapter
        from app.services.workload_classifier import WorkloadClassifier

        clf = WorkloadClassifier()
        catalog = MockCatalogAdapter()
        item = catalog.get_item("sandbox-minimal")
        assert item is not None

        profile = clf.classify(item, _request(catalog_item_id="sandbox-minimal"))
        assert profile.workload_type == WorkloadType.LIGHTWEIGHT
