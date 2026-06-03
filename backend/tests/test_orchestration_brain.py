"""
TDD: Orchestration Brain — compose workload classification, placement,
feedback, and DeepField signals into unified provisioning decisions.
Tests every degradation path.
"""
import os
from datetime import datetime

import pytest

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("INTEGRATION_API_KEY", "test-integration-key")

from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.feedback import ProvisioningOutcome
from app.domain.models import CatalogItem, LabRequest
from app.domain.orchestration import (
    DeepFieldSignal,
    HealthAlert,
    OrchestrationDecision,
    RebalanceAction,
)
from app.domain.placement import ClusterCapacity
from app.domain.workload import WorkloadProfile, WorkloadType


def _catalog_item(**overrides):
    defaults = dict(
        catalog_item_id="inference-overdrive",
        display_name="Inference Overdrive",
        description="Dual-path AI inference gateway",
        category=CatalogCategory.QUICK_START,
        status=CatalogStatus.ACTIVE,
        required_capabilities=["openshift", "model_endpoint"],
        default_hardware_profile="gaudi-endpoint",
        default_quota_profile="standard",
    )
    defaults.update(overrides)
    return CatalogItem(**defaults)


def _request(**overrides):
    defaults = dict(
        tenant_id="test",
        requester_id="user-1",
        catalog_item_id="inference-overdrive",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(overrides)
    return LabRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Domain Models
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationModels:

    def test_deepfield_signal(self):
        s = DeepFieldSignal(cluster_name="c1", metric_type="cpu_utilization", value=0.85, status="warning")
        assert s.status == "warning"

    def test_orchestration_decision(self):
        d = OrchestrationDecision(
            request_id="req-1",
            recommended_cluster="cluster-a",
            recommended_hardware="gaudi-endpoint",
            confidence=0.85,
            signals_used=["stargate_capacity", "deepfield_metrics"],
        )
        assert d.decision_id
        assert len(d.signals_used) == 2

    def test_rebalance_action(self):
        a = RebalanceAction(session_id="s-1", from_cluster="cluster-a", reason="overloaded")
        assert a.urgency == "medium"

    def test_health_alert(self):
        h = HealthAlert(
            cluster_name="cluster-a",
            alert_type="cpu_saturation",
            severity="critical",
            recommended_action="drain workloads",
        )
        assert h.alert_id
        assert h.severity == "critical"


# ═══════════════════════════════════════════════════════════════════════════════
# OrchestrationBrain — Full pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrationBrain:

    def _brain(self, deepfield=None, stargate_clusters=None, feedback_outcomes=None):
        from app.adapters.mock.deepfield import MockDeepFieldAdapter, MockDeepFieldDown
        from app.services.feedback_tracker import FeedbackTracker
        from app.services.orchestration_brain import OrchestrationBrain
        from app.services.placement import PlacementService
        from app.services.workload_classifier import WorkloadClassifier

        placement = PlacementService()
        if stargate_clusters:
            placement._capacity_cache = {
                name: ClusterCapacity(cluster_name=name, score=score, health_status="healthy")
                for name, score in stargate_clusters.items()
            }
            placement._cache_updated_at = datetime.utcnow()

        tracker = FeedbackTracker()
        if feedback_outcomes:
            for o in feedback_outcomes:
                tracker.record_outcome(o)

        df = deepfield if deepfield is not None else MockDeepFieldAdapter()

        return OrchestrationBrain(
            classifier=WorkloadClassifier(),
            placement=placement,
            feedback_tracker=tracker,
            deepfield=df,
        )

    def test_importable(self):
        from app.services.orchestration_brain import OrchestrationBrain
        assert OrchestrationBrain is not None

    def test_full_decision_all_signals(self):
        brain = self._brain(stargate_clusters={"cluster-a": 90.0, "cluster-b": 70.0})
        decision = brain.decide(_request(), _catalog_item())

        assert isinstance(decision, OrchestrationDecision)
        assert decision.recommended_hardware is not None
        assert decision.recommended_quota is not None
        assert decision.confidence > 0
        assert len(decision.signals_used) >= 2

    def test_decision_includes_workload_profile(self):
        brain = self._brain(stargate_clusters={"cluster-a": 90.0})
        decision = brain.decide(_request(), _catalog_item())

        assert decision.workload_profile is not None
        assert decision.workload_profile.workload_type == WorkloadType.GPU_INFERENCE

    def test_decision_recommends_cluster_from_stargate(self):
        brain = self._brain(stargate_clusters={"cluster-a": 90.0, "cluster-b": 70.0})
        decision = brain.decide(_request(), _catalog_item())
        assert decision.recommended_cluster == "cluster-a"

    def test_decision_has_rationale(self):
        brain = self._brain(stargate_clusters={"cluster-a": 90.0})
        decision = brain.decide(_request(), _catalog_item())
        assert len(decision.rationale) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Degradation paths
# ═══════════════════════════════════════════════════════════════════════════════


class TestDegradationPaths:

    def _brain(self, **kw):
        return TestOrchestrationBrain._brain(self, **kw)

    def test_stargate_down_still_decides(self):
        brain = self._brain(stargate_clusters=None)
        decision = brain.decide(_request(), _catalog_item())

        assert isinstance(decision, OrchestrationDecision)
        assert decision.recommended_hardware is not None
        assert "stargate_capacity" not in decision.signals_used

    def test_deepfield_down_still_decides(self):
        from app.adapters.mock.deepfield import MockDeepFieldDown
        brain = self._brain(
            stargate_clusters={"cluster-a": 90.0},
            deepfield=MockDeepFieldDown(),
        )
        decision = brain.decide(_request(), _catalog_item())

        assert isinstance(decision, OrchestrationDecision)
        assert decision.recommended_cluster == "cluster-a"
        assert "deepfield_metrics" not in decision.signals_used

    def test_both_external_down_still_decides(self):
        from app.adapters.mock.deepfield import MockDeepFieldDown
        brain = self._brain(stargate_clusters=None, deepfield=MockDeepFieldDown())
        decision = brain.decide(_request(), _catalog_item())

        assert isinstance(decision, OrchestrationDecision)
        assert decision.recommended_hardware is not None
        assert decision.confidence < 0.5

    def test_all_down_plus_no_feedback_uses_static(self):
        from app.adapters.mock.deepfield import MockDeepFieldDown
        brain = self._brain(stargate_clusters=None, deepfield=MockDeepFieldDown())
        decision = brain.decide(_request(), _catalog_item())

        assert decision.recommended_hardware in ("gaudi-endpoint", "gaudi-direct", "mixed-overdrive", "xeon-basic", "xeon6")

    def test_feedback_only_adjusts_decision(self):
        from app.adapters.mock.deepfield import MockDeepFieldDown
        outcomes = [
            ProvisioningOutcome(
                session_id=f"s-{i}", request_id=f"r-{i}",
                catalog_item_id="inference-overdrive",
                cluster_name="cluster-a", hardware_profile="gaudi-endpoint",
                quota_profile="standard", success=True, provision_latency_ms=2000,
                validation_passed=True,
            )
            for i in range(10)
        ]
        brain = self._brain(
            stargate_clusters={"cluster-a": 80.0, "cluster-b": 85.0},
            deepfield=MockDeepFieldDown(),
            feedback_outcomes=outcomes,
        )
        decision = brain.decide(_request(), _catalog_item())
        assert "feedback_history" in decision.signals_used


# ═══════════════════════════════════════════════════════════════════════════════
# DeepField signal integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeepFieldIntegration:

    def _brain(self, **kw):
        return TestOrchestrationBrain._brain(self, **kw)

    def test_critical_signals_reduce_cluster_score(self):
        from app.adapters.mock.deepfield import MockUnhealthyDeepFieldAdapter
        brain = self._brain(
            stargate_clusters={"cluster-a": 95.0, "healthy-cluster": 70.0},
            deepfield=MockUnhealthyDeepFieldAdapter(unhealthy_cluster="cluster-a"),
        )
        decision = brain.decide(_request(), _catalog_item())
        assert decision.recommended_cluster == "healthy-cluster"

    def test_deepfield_signals_listed_in_signals_used(self):
        brain = self._brain(stargate_clusters={"mock-cluster-1": 90.0})
        decision = brain.decide(_request(), _catalog_item())
        assert "deepfield_metrics" in decision.signals_used


# ═══════════════════════════════════════════════════════════════════════════════
# Health alerts
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealthAlerts:

    def _brain(self, **kw):
        return TestOrchestrationBrain._brain(self, **kw)

    def test_proactive_health_check_detects_critical(self):
        from app.adapters.mock.deepfield import MockUnhealthyDeepFieldAdapter
        brain = self._brain(
            deepfield=MockUnhealthyDeepFieldAdapter(unhealthy_cluster="cluster-a"),
        )
        alerts = brain.proactive_health_check()
        assert len(alerts) >= 1
        assert any(a.cluster_name == "cluster-a" and a.severity == "critical" for a in alerts)

    def test_proactive_health_check_no_alerts_when_healthy(self):
        brain = self._brain()
        alerts = brain.proactive_health_check()
        assert len(alerts) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration with ProvisioningService
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrainProvisioningIntegration:

    def test_provisioning_uses_brain_when_available(self):
        from app.adapters.mock.deepfield import MockDeepFieldAdapter
        from app.services.feedback_tracker import FeedbackTracker
        from app.services.orchestration_brain import OrchestrationBrain
        from app.services.placement import PlacementService
        from app.services.provisioning import ProvisioningService
        from app.services.workload_classifier import WorkloadClassifier

        brain = OrchestrationBrain(
            classifier=WorkloadClassifier(),
            placement=PlacementService(),
            feedback_tracker=FeedbackTracker(),
            deepfield=MockDeepFieldAdapter(),
        )
        svc = ProvisioningService(brain=brain)

        req = _request(catalog_item_id="inference-overdrive-quickstart")
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        assert session is not None

    def test_provisioning_works_without_brain(self):
        from app.services.provisioning import ProvisioningService

        svc = ProvisioningService()
        req = _request(catalog_item_id="inference-overdrive-quickstart")
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        assert session is not None

    def test_provisioning_degrades_when_brain_raises(self):
        from app.services.provisioning import ProvisioningService

        class FailingBrain:
            def decide(self, *a, **kw):
                raise RuntimeError("brain error")

        svc = ProvisioningService(brain=FailingBrain())
        req = _request(catalog_item_id="inference-overdrive-quickstart")
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        assert session is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Confidence scoring
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfidenceScoring:

    def _brain(self, **kw):
        return TestOrchestrationBrain._brain(self, **kw)

    def test_all_signals_high_confidence(self):
        outcomes = [
            ProvisioningOutcome(
                session_id=f"s-{i}", request_id=f"r-{i}",
                catalog_item_id="inference-overdrive",
                cluster_name="cluster-a", hardware_profile="gaudi-endpoint",
                quota_profile="standard", success=True, provision_latency_ms=2000,
                validation_passed=True,
            )
            for i in range(10)
        ]
        brain = self._brain(
            stargate_clusters={"cluster-a": 90.0},
            feedback_outcomes=outcomes,
        )
        decision = brain.decide(_request(), _catalog_item())
        assert decision.confidence >= 0.6

    def test_no_external_signals_low_confidence(self):
        from app.adapters.mock.deepfield import MockDeepFieldDown
        brain = self._brain(stargate_clusters=None, deepfield=MockDeepFieldDown())
        decision = brain.decide(_request(), _catalog_item())
        assert decision.confidence < 0.5
