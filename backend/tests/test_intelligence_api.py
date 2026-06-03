"""
TDD: Intelligence API router — fleet health, decisions, simulate, feedback endpoints.
"""
import os
from unittest.mock import patch

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("INTEGRATION_API_KEY", "test-integration-key")

from fastapi.testclient import TestClient

from app.domain.enums import CatalogCategory
from app.domain.models import LabRequest
from app.main import app
from app.services.provisioning import ProvisioningService

client = TestClient(app)


def _req(**kw):
    defaults = dict(
        tenant_id="test",
        requester_id="user-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(kw)
    return LabRequest(**defaults)


def _provision(svc, **kw):
    r = svc.submit_request(_req(**kw))
    return svc.provision(r.request_id)


class TestFleetHealth:

    def test_fleet_health_returns_200(self):
        resp = client.get("/api/v1/intelligence/fleet-health")
        assert resp.status_code == 200
        data = resp.json()
        assert "clusters" in data
        assert "alerts" in data

    def test_fleet_health_returns_empty_when_no_placement(self):
        resp = client.get("/api/v1/intelligence/fleet-health")
        data = resp.json()
        assert data["clusters"] == []
        assert data["alerts"] == []


class TestDecisionEndpoint:

    def test_decision_404_for_unknown_request(self):
        resp = client.get("/api/v1/intelligence/decision/nonexistent")
        assert resp.status_code == 404

    def test_decision_returns_data_when_stored(self):
        from app.api.deps import provisioning_service
        session = _provision(provisioning_service)
        session_with_decision = session.model_copy(update={
            "resources": {**session.resources, "decision": {
                "decision_id": "test-dec-1",
                "request_id": session.request_id,
                "recommended_hardware": "gaudi-endpoint",
                "recommended_quota": "standard",
                "confidence": 0.85,
                "rationale": "test rationale",
                "signals_used": ["workload_classification"],
                "fallback_chain": [],
            }},
        })
        provisioning_service._sessions[session.session_id] = session_with_decision

        resp = client.get(f"/api/v1/intelligence/decision/{session.request_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_hardware"] == "gaudi-endpoint"
        assert data["confidence"] == 0.85


class TestSimulate:

    def test_simulate_returns_503_without_brain(self):
        resp = client.post("/api/v1/intelligence/simulate", json={
            "catalog_item_id": "inference-overdrive-quickstart",
            "tenant_id": "test",
        })
        assert resp.status_code == 503

    def test_simulate_returns_404_for_unknown_catalog(self):
        from app.api.deps import provisioning_service
        from app.services.orchestration_brain import OrchestrationBrain
        from app.services.workload_classifier import WorkloadClassifier

        provisioning_service.brain = OrchestrationBrain(classifier=WorkloadClassifier())
        try:
            resp = client.post("/api/v1/intelligence/simulate", json={
                "catalog_item_id": "nonexistent",
                "tenant_id": "test",
            })
            assert resp.status_code == 404
        finally:
            provisioning_service.brain = None


class TestClusterSignals:

    def test_cluster_signals_returns_empty_without_deepfield(self):
        resp = client.get("/api/v1/intelligence/cluster/test-cluster/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["signals"] == []


class TestFeedbackEndpoints:

    def test_feedback_summary_returns_empty(self):
        resp = client.get("/api/v1/admin/feedback/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summaries"] == []

    def test_feedback_by_cluster_returns_empty(self):
        resp = client.get("/api/v1/admin/feedback/cluster/test-cluster")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summaries"] == []

    def test_feedback_by_catalog_returns_empty(self):
        resp = client.get("/api/v1/admin/feedback/catalog/test-item")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summaries"] == []

    def test_feedback_summary_with_data(self):
        from app.api.deps import provisioning_service
        from app.domain.feedback import ProvisioningOutcome
        from app.services.feedback_tracker import FeedbackTracker

        tracker = FeedbackTracker()
        for i in range(5):
            tracker.record_outcome(ProvisioningOutcome(
                session_id=f"s-{i}", request_id=f"r-{i}",
                catalog_item_id="inference-overdrive",
                cluster_name="cluster-a", hardware_profile="gaudi-endpoint",
                quota_profile="standard", success=True,
                provision_latency_ms=2000, validation_passed=True,
            ))

        provisioning_service.feedback_tracker = tracker
        try:
            resp = client.get("/api/v1/admin/feedback/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["summaries"]) == 1
            assert data["summaries"][0]["success_rate"] == 1.0
        finally:
            provisioning_service.feedback_tracker = None
