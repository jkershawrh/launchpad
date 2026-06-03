from __future__ import annotations

from app.domain.placement import PlacementRecommendation


class MockPlacementService:

    def recommend_cluster(self, hardware_profile: str, **kwargs) -> PlacementRecommendation:
        return PlacementRecommendation(
            cluster_name="mock-cluster-1",
            score=90.0,
            reasoning="mock placement",
            source="cache",
        )

    def refresh_capacity_cache(self) -> int:
        return 1

    def get_capacity_snapshot(self):
        return []


class MockNoCapacityPlacementService:

    def recommend_cluster(self, hardware_profile: str, **kwargs) -> PlacementRecommendation:
        return PlacementRecommendation(
            fallback=True,
            reasoning="no capacity data",
        )

    def refresh_capacity_cache(self) -> int:
        return 0

    def get_capacity_snapshot(self):
        return []
