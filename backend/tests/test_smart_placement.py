"""
TDD: Smart placement — PlacementService recommends clusters based on
StarGate capacity scores, with caching and graceful degradation.
"""
import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("INTEGRATION_API_KEY", "test-integration-key")

from app.domain.enums import CatalogCategory
from app.domain.models import CatalogItem, LabRequest
from app.domain.placement import ClusterCapacity, PlacementDecision, PlacementRecommendation


# ═══════════════════════════════════════════════════════════════════════════════
# Domain Models
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlacementModels:

    def test_cluster_capacity_defaults(self):
        cap = ClusterCapacity(cluster_name="cluster-a")
        assert cap.cluster_name == "cluster-a"
        assert cap.score == 0.0
        assert cap.health_status == "unknown"

    def test_cluster_capacity_with_values(self):
        cap = ClusterCapacity(
            cluster_name="cluster-a",
            score=85.5,
            cpu_utilization=0.42,
            gpu_available=True,
            health_status="healthy",
        )
        assert cap.score == 85.5
        assert cap.gpu_available is True

    def test_placement_recommendation_defaults(self):
        rec = PlacementRecommendation()
        assert rec.cluster_name is None
        assert rec.fallback is False
        assert rec.source == "none"

    def test_placement_recommendation_with_cluster(self):
        rec = PlacementRecommendation(
            cluster_name="cluster-b",
            score=90.0,
            reasoning="highest capacity",
            source="cache",
        )
        assert rec.cluster_name == "cluster-b"
        assert rec.source == "cache"

    def test_placement_decision_audit_trail(self):
        dec = PlacementDecision(
            request_id="req-001",
            recommended_cluster="cluster-a",
            selected_cluster="cluster-a",
            hardware_profile="gaudi-endpoint",
            score=85.0,
            decision_source="live",
        )
        assert dec.request_id == "req-001"
        assert dec.decision_id  # auto-generated uuid


# ═══════════════════════════════════════════════════════════════════════════════
# PlacementService
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlacementService:

    def test_importable(self):
        from app.services.placement import PlacementService
        svc = PlacementService()
        assert svc is not None

    def test_recommend_with_warm_cache(self):
        from app.services.placement import PlacementService
        svc = PlacementService()
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=80.0, health_status="healthy"),
            "cluster-b": ClusterCapacity(cluster_name="cluster-b", score=95.0, health_status="healthy"),
        }
        svc._cache_updated_at = datetime.utcnow()

        rec = svc.recommend_cluster("gaudi-endpoint")
        assert rec.cluster_name == "cluster-b"
        assert rec.source == "cache"
        assert not rec.fallback

    def test_recommend_excludes_clusters(self):
        from app.services.placement import PlacementService
        svc = PlacementService()
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=95.0, health_status="healthy"),
            "cluster-b": ClusterCapacity(cluster_name="cluster-b", score=80.0, health_status="healthy"),
        }
        svc._cache_updated_at = datetime.utcnow()

        rec = svc.recommend_cluster("gaudi-endpoint", exclude=["cluster-a"])
        assert rec.cluster_name == "cluster-b"

    def test_recommend_filters_unhealthy(self):
        from app.services.placement import PlacementService
        svc = PlacementService()
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=95.0, health_status="degraded"),
            "cluster-b": ClusterCapacity(cluster_name="cluster-b", score=60.0, health_status="healthy"),
        }
        svc._cache_updated_at = datetime.utcnow()

        rec = svc.recommend_cluster("gaudi-endpoint")
        assert rec.cluster_name == "cluster-b"

    def test_recommend_fallback_when_cache_empty(self):
        from app.services.placement import PlacementService
        svc = PlacementService()
        rec = svc.recommend_cluster("gaudi-endpoint")
        assert rec.cluster_name is None
        assert rec.fallback is True
        assert rec.source == "none"

    def test_recommend_fallback_when_cache_expired(self):
        from app.services.placement import PlacementService
        svc = PlacementService(cache_ttl_seconds=60)
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=80.0, health_status="healthy"),
        }
        svc._cache_updated_at = datetime.utcnow() - timedelta(seconds=120)

        rec = svc.recommend_cluster("gaudi-endpoint")
        assert rec.fallback is True

    def test_recommend_fallback_when_all_excluded(self):
        from app.services.placement import PlacementService
        svc = PlacementService()
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=90.0, health_status="healthy"),
        }
        svc._cache_updated_at = datetime.utcnow()

        rec = svc.recommend_cluster("gaudi-endpoint", exclude=["cluster-a"])
        assert rec.cluster_name is None
        assert rec.fallback is True

    def test_refresh_capacity_cache_from_stargate(self):
        from app.services.placement import PlacementService
        svc = PlacementService(stargate_url="https://stargate.test")

        mock_clusters = [
            {"cluster": "cluster-a", "score": 85.0, "status": "healthy"},
            {"cluster": "cluster-b", "score": 70.0, "status": "healthy"},
        ]
        with patch("app.services.placement.get_cluster_capacity", new_callable=AsyncMock, return_value=mock_clusters):
            count = svc.refresh_capacity_cache()

        assert count == 2
        assert "cluster-a" in svc._capacity_cache
        assert svc._capacity_cache["cluster-a"].score == 85.0

    def test_refresh_cache_stargate_down_keeps_old(self):
        from app.services.placement import PlacementService
        svc = PlacementService(stargate_url="https://stargate.test")
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=80.0, health_status="healthy"),
        }
        old_updated = datetime.utcnow() - timedelta(seconds=30)
        svc._cache_updated_at = old_updated

        with patch("app.services.placement.get_cluster_capacity", new_callable=AsyncMock, return_value=[]):
            count = svc.refresh_capacity_cache()

        assert count == 0
        assert "cluster-a" in svc._capacity_cache

    def test_get_capacity_snapshot(self):
        from app.services.placement import PlacementService
        svc = PlacementService()
        svc._capacity_cache = {
            "cluster-a": ClusterCapacity(cluster_name="cluster-a", score=80.0, health_status="healthy"),
            "cluster-b": ClusterCapacity(cluster_name="cluster-b", score=70.0, health_status="healthy"),
        }
        snapshot = svc.get_capacity_snapshot()
        assert len(snapshot) == 2
        assert all(isinstance(c, ClusterCapacity) for c in snapshot)


# ═══════════════════════════════════════════════════════════════════════════════
# Mock Placement
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockPlacement:

    def test_mock_placement_returns_deterministic(self):
        from app.adapters.mock.placement import MockPlacementService
        svc = MockPlacementService()
        rec = svc.recommend_cluster("gaudi-endpoint")
        assert rec.cluster_name == "mock-cluster-1"
        assert rec.source == "cache"

    def test_mock_no_capacity_returns_fallback(self):
        from app.adapters.mock.placement import MockNoCapacityPlacementService
        svc = MockNoCapacityPlacementService()
        rec = svc.recommend_cluster("gaudi-endpoint")
        assert rec.cluster_name is None
        assert rec.fallback is True


# ═══════════════════════════════════════════════════════════════════════════════
# Integration with ProvisioningService
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlacementIntegration:

    def test_provisioning_uses_placement_recommendation(self):
        from app.adapters.mock.placement import MockPlacementService
        from app.services.provisioning import ProvisioningService

        placement = MockPlacementService()
        svc = ProvisioningService(placement=placement)

        req = LabRequest(
            tenant_id="test",
            requester_id="user-1",
            catalog_item_id="inference-overdrive-quickstart",
            requested_mode=CatalogCategory.QUICK_START,
        )
        accepted = svc.submit_request(req)
        session = svc.provision(accepted.request_id)
        assert session is not None

    def test_provisioning_works_without_placement(self):
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

    def test_provisioning_degrades_when_placement_raises(self):
        from app.services.provisioning import ProvisioningService

        class FailingPlacement:
            def recommend_cluster(self, *a, **kw):
                raise RuntimeError("StarGate exploded")

        svc = ProvisioningService(placement=FailingPlacement())
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
# RHDP Pool with preferred_cluster
# ═══════════════════════════════════════════════════════════════════════════════


class TestPoolPreferredCluster:

    def test_build_cloud_selector_without_preference(self):
        from app.adapters.rhdp.pool import RHDPPoolAdapter
        adapter = RHDPPoolAdapter(sandbox_api=MagicMock())
        selector = adapter._build_cloud_selector("gaudi-endpoint")
        assert "gaudi" in selector
        assert "cluster_name" not in selector

    def test_build_cloud_selector_with_preference(self):
        from app.adapters.rhdp.pool import RHDPPoolAdapter
        adapter = RHDPPoolAdapter(sandbox_api=MagicMock())
        selector = adapter._build_cloud_selector("gaudi-endpoint", preferred_cluster="cluster-a")
        assert selector.get("cluster_name") == "cluster-a"
        assert selector.get("gaudi") == "true"


# ═══════════════════════════════════════════════════════════════════════════════
# Celery Task
# ═══════════════════════════════════════════════════════════════════════════════


class TestCapacitySyncTask:

    def test_capacity_sync_task_importable(self):
        from tasks.capacity_sync import sync_cluster_capacity
        assert callable(sync_cluster_capacity)
