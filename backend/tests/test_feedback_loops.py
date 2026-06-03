"""
TDD: Feedback loops — track provisioning outcomes, compute success rates,
rank clusters, avoid failing combinations, and feed history into
placement and workload classification decisions.
"""
import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("INTEGRATION_API_KEY", "test-integration-key")

from app.domain.enums import CatalogCategory
from app.domain.feedback import FeedbackSummary, ProvisioningOutcome
from app.domain.models import LabRequest
from app.domain.placement import ClusterCapacity


def _outcome(success=True, **overrides):
    defaults = dict(
        session_id="session-001",
        request_id="req-001",
        catalog_item_id="inference-overdrive",
        cluster_name="cluster-a",
        hardware_profile="gaudi-endpoint",
        quota_profile="standard",
        success=success,
        provision_latency_ms=3500,
        validation_passed=success,
    )
    defaults.update(overrides)
    return ProvisioningOutcome(**defaults)


def _request(**overrides):
    defaults = dict(
        tenant_id="test",
        requester_id="user-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(overrides)
    return LabRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Domain Models
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedbackModels:

    def test_provisioning_outcome_defaults(self):
        o = _outcome()
        assert o.outcome_id
        assert o.success is True
        assert o.provision_latency_ms == 3500

    def test_provisioning_outcome_failure(self):
        o = _outcome(success=False, failure_reason="namespace stuck in Terminating")
        assert o.success is False
        assert o.failure_reason == "namespace stuck in Terminating"

    def test_feedback_summary_defaults(self):
        s = FeedbackSummary(
            catalog_item_id="test",
            cluster_name="cluster-a",
            hardware_profile="gaudi-endpoint",
        )
        assert s.total_attempts == 0
        assert s.success_rate == 0.0
        assert s.recommendation == "acceptable"

    def test_feedback_summary_with_data(self):
        s = FeedbackSummary(
            catalog_item_id="test",
            cluster_name="cluster-a",
            hardware_profile="gaudi-endpoint",
            total_attempts=20,
            success_count=18,
            success_rate=0.9,
            avg_latency_ms=2500.0,
            confidence=0.85,
            recommendation="preferred",
        )
        assert s.success_rate == 0.9
        assert s.recommendation == "preferred"


# ═══════════════════════════════════════════════════════════════════════════════
# FeedbackTracker — Recording outcomes
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecordOutcome:

    def test_importable(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()
        assert tracker is not None

    def test_record_outcome_persists(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()
        outcome = _outcome()
        tracker.record_outcome(outcome)

        outcomes = tracker.get_outcomes(catalog_item_id="inference-overdrive")
        assert len(outcomes) == 1
        assert outcomes[0].session_id == "session-001"

    def test_record_multiple_outcomes(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(5):
            tracker.record_outcome(_outcome(session_id=f"session-{i}"))

        outcomes = tracker.get_outcomes(catalog_item_id="inference-overdrive")
        assert len(outcomes) == 5

    def test_record_failure_outcome(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()
        tracker.record_outcome(_outcome(success=False, failure_reason="pod crashloop"))

        outcomes = tracker.get_outcomes(catalog_item_id="inference-overdrive")
        assert len(outcomes) == 1
        assert outcomes[0].success is False


# ═══════════════════════════════════════════════════════════════════════════════
# FeedbackTracker — Success rate calculation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSuccessRate:

    def test_success_rate_all_pass(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(10):
            tracker.record_outcome(_outcome(session_id=f"s-{i}"))

        summary = tracker.get_summary("inference-overdrive", "cluster-a", "gaudi-endpoint")
        assert summary is not None
        assert summary.success_rate == 1.0
        assert summary.total_attempts == 10

    def test_success_rate_mixed(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(7):
            tracker.record_outcome(_outcome(session_id=f"s-{i}", success=True))
        for i in range(3):
            tracker.record_outcome(_outcome(session_id=f"f-{i}", success=False, failure_reason="timeout"))

        summary = tracker.get_summary("inference-overdrive", "cluster-a", "gaudi-endpoint")
        assert summary is not None
        assert summary.success_rate == pytest.approx(0.7, abs=0.01)
        assert summary.total_attempts == 10
        assert summary.success_count == 7

    def test_success_rate_all_fail(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(5):
            tracker.record_outcome(_outcome(session_id=f"f-{i}", success=False, failure_reason="crash"))

        summary = tracker.get_summary("inference-overdrive", "cluster-a", "gaudi-endpoint")
        assert summary is not None
        assert summary.success_rate == 0.0
        assert summary.last_failure_reason == "crash"

    def test_summary_returns_none_when_no_data(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        summary = tracker.get_summary("nonexistent", "cluster-x", "gaudi-endpoint")
        assert summary is None

    def test_avg_latency_calculation(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        tracker.record_outcome(_outcome(session_id="s-1", provision_latency_ms=2000))
        tracker.record_outcome(_outcome(session_id="s-2", provision_latency_ms=4000))

        summary = tracker.get_summary("inference-overdrive", "cluster-a", "gaudi-endpoint")
        assert summary.avg_latency_ms == pytest.approx(3000.0)


# ═══════════════════════════════════════════════════════════════════════════════
# FeedbackTracker — Cluster rankings
# ═══════════════════════════════════════════════════════════════════════════════


class TestClusterRankings:

    def test_cluster_rankings_sorted_by_success_rate(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(10):
            tracker.record_outcome(_outcome(session_id=f"a-{i}", cluster_name="cluster-a", success=True))
        for i in range(10):
            tracker.record_outcome(_outcome(
                session_id=f"b-{i}", cluster_name="cluster-b",
                success=(i < 5), failure_reason="fail" if i >= 5 else None,
            ))

        rankings = tracker.get_cluster_rankings("inference-overdrive", "gaudi-endpoint")
        assert len(rankings) == 2
        assert rankings[0].cluster_name == "cluster-a"
        assert rankings[0].success_rate == 1.0
        assert rankings[1].cluster_name == "cluster-b"
        assert rankings[1].success_rate == pytest.approx(0.5)

    def test_cluster_rankings_empty_when_no_data(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        rankings = tracker.get_cluster_rankings("nonexistent", "gaudi-endpoint")
        assert rankings == []

    def test_hardware_rankings(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(10):
            tracker.record_outcome(_outcome(
                session_id=f"g-{i}", hardware_profile="gaudi-endpoint", success=True,
            ))
        for i in range(10):
            tracker.record_outcome(_outcome(
                session_id=f"x-{i}", hardware_profile="xeon-basic",
                success=(i < 3), failure_reason="fail" if i >= 3 else None,
            ))

        rankings = tracker.get_hardware_rankings("inference-overdrive")
        assert len(rankings) == 2
        assert rankings[0].hardware_profile == "gaudi-endpoint"
        assert rankings[1].hardware_profile == "xeon-basic"


# ═══════════════════════════════════════════════════════════════════════════════
# FeedbackTracker — should_avoid
# ═══════════════════════════════════════════════════════════════════════════════


class TestShouldAvoid:

    def test_should_avoid_failing_cluster(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(6):
            tracker.record_outcome(_outcome(
                session_id=f"f-{i}", success=False, failure_reason="crash",
            ))

        assert tracker.should_avoid("inference-overdrive", "cluster-a", "gaudi-endpoint") is True

    def test_should_not_avoid_healthy_cluster(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(10):
            tracker.record_outcome(_outcome(session_id=f"s-{i}", success=True))

        assert tracker.should_avoid("inference-overdrive", "cluster-a", "gaudi-endpoint") is False

    def test_should_not_avoid_with_insufficient_samples(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(3):
            tracker.record_outcome(_outcome(session_id=f"f-{i}", success=False, failure_reason="crash"))

        assert tracker.should_avoid("inference-overdrive", "cluster-a", "gaudi-endpoint") is False

    def test_should_not_avoid_unknown_combination(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        assert tracker.should_avoid("nonexistent", "cluster-x", "gaudi-endpoint") is False


# ═══════════════════════════════════════════════════════════════════════════════
# FeedbackTracker — Confidence scoring
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfidence:

    def test_confidence_increases_with_samples(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        tracker.record_outcome(_outcome(session_id="s-1"))
        s1 = tracker.get_summary("inference-overdrive", "cluster-a", "gaudi-endpoint")

        for i in range(19):
            tracker.record_outcome(_outcome(session_id=f"s-{i+2}"))
        s20 = tracker.get_summary("inference-overdrive", "cluster-a", "gaudi-endpoint")

        assert s20.confidence > s1.confidence

    def test_recommendation_from_success_rate(self):
        from app.services.feedback_tracker import FeedbackTracker
        tracker = FeedbackTracker()

        for i in range(10):
            tracker.record_outcome(_outcome(session_id=f"s-{i}", success=True))

        summary = tracker.get_summary("inference-overdrive", "cluster-a", "gaudi-endpoint")
        assert summary.recommendation == "preferred"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: PlacementService uses feedback
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlacementFeedbackIntegration:

    def test_placement_excludes_avoided_clusters(self):
        from app.services.feedback_tracker import FeedbackTracker
        from app.services.placement import PlacementService
        from app.domain.placement import ClusterCapacity

        tracker = FeedbackTracker()
        for i in range(6):
            tracker.record_outcome(_outcome(
                session_id=f"f-{i}", cluster_name="cluster-a", success=False, failure_reason="crash",
            ))

        svc = PlacementService()
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=95.0, health_status="healthy"),
            "cluster-b": ClusterCapacity(cluster_name="cluster-b", score=70.0, health_status="healthy"),
        }
        svc._cache_updated_at = datetime.utcnow()

        rec = svc.recommend_cluster(
            "gaudi-endpoint",
            feedback_tracker=tracker,
            catalog_item_id="inference-overdrive",
        )
        assert rec.cluster_name == "cluster-b"

    def test_placement_works_without_feedback(self):
        from app.services.placement import PlacementService
        from app.domain.placement import ClusterCapacity

        svc = PlacementService()
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=95.0, health_status="healthy"),
        }
        svc._cache_updated_at = datetime.utcnow()

        rec = svc.recommend_cluster("gaudi-endpoint")
        assert rec.cluster_name == "cluster-a"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: ProvisioningService records outcomes
# ═══════════════════════════════════════════════════════════════════════════════


class TestProvisioningFeedbackIntegration:

    def test_provisioning_records_outcome_after_validation(self):
        from app.services.feedback_tracker import FeedbackTracker
        from app.services.provisioning import ProvisioningService

        tracker = FeedbackTracker()
        svc = ProvisioningService(feedback_tracker=tracker)

        req = _request()
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        svc.validate_session(session.session_id)

        outcomes = tracker.get_outcomes(catalog_item_id="inference-overdrive-quickstart")
        assert len(outcomes) == 1
        assert outcomes[0].validation_passed is True

    def test_provisioning_works_without_feedback_tracker(self):
        from app.services.provisioning import ProvisioningService

        svc = ProvisioningService()
        req = _request()
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        svc.validate_session(session.session_id)

    def test_full_loop_provision_validate_record_next_provision_uses_history(self):
        from app.services.feedback_tracker import FeedbackTracker
        from app.services.provisioning import ProvisioningService

        tracker = FeedbackTracker()
        svc = ProvisioningService(feedback_tracker=tracker)

        req1 = _request(requester_id="user-1")
        accepted1 = svc.submit_request(req1)
        session1 = svc.provision(accepted1.request_id)
        svc.validate_session(session1.session_id)

        assert len(tracker.get_outcomes(catalog_item_id="inference-overdrive-quickstart")) == 1

        req2 = _request(requester_id="user-2")
        accepted2 = svc.submit_request(req2)
        session2 = svc.provision(accepted2.request_id)
        assert session2 is not None
