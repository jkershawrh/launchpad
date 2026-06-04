from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.adapters.rhdp.stargate_capacity import get_cluster_capacity
from app.domain.placement import ClusterCapacity, PlacementRecommendation

logger = logging.getLogger("launchpad.placement")

DEFAULT_CACHE_TTL = 120


class PlacementService:

    def __init__(
        self,
        stargate_url: Optional[str] = None,
        stargate_api_key: Optional[str] = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL,
    ):
        self.stargate_url = stargate_url
        self.stargate_api_key = stargate_api_key
        self.cache_ttl_seconds = cache_ttl_seconds
        self._capacity_cache: Dict[str, ClusterCapacity] = {}
        self._cache_updated_at: Optional[datetime] = None

    def recommend_cluster(
        self,
        hardware_profile: str,
        capabilities: Optional[Dict[str, str]] = None,
        exclude: Optional[List[str]] = None,
        feedback_tracker=None,
        catalog_item_id: Optional[str] = None,
    ) -> PlacementRecommendation:
        exclude = list(exclude or [])

        if feedback_tracker and catalog_item_id:
            for name in list(self._capacity_cache.keys()):
                if feedback_tracker.should_avoid(catalog_item_id, name, hardware_profile):
                    exclude.append(name)

        if not self._cache_is_valid():
            return PlacementRecommendation(fallback=True, reasoning="no capacity data available")

        candidates = [
            c for c in self._capacity_cache.values()
            if c.cluster_name not in exclude and c.health_status == "healthy"
        ]

        if not candidates:
            return PlacementRecommendation(fallback=True, reasoning="no healthy clusters available")

        if feedback_tracker and catalog_item_id:
            for c in candidates:
                summary = feedback_tracker.get_summary(catalog_item_id, c.cluster_name, hardware_profile)
                if summary and summary.total_attempts >= 5:
                    c.score = c.score * summary.success_rate

        candidates.sort(key=lambda c: -c.score)
        best = candidates[0]

        return PlacementRecommendation(
            cluster_name=best.cluster_name,
            score=best.score,
            reasoning=f"highest capacity score ({best.score})",
            source="cache",
        )

    def refresh_capacity_cache(self) -> int:
        if not self.stargate_url:
            return 0
        try:
            import httpx
            resp = httpx.get(
                f"{self.stargate_url}/api/v1/clusters/capacity",
                timeout=10,
                verify=False,
            )
            resp.raise_for_status()
            clusters = resp.json().get("clusters", [])
        except Exception as e:
            logger.debug("Failed to refresh capacity cache: %s", e)
            return 0

        if not clusters:
            return 0

        new_cache = {}
        for c in clusters:
            cpu_pct = c.get("cpu_pct")
            new_cache[c["cluster"]] = ClusterCapacity(
                cluster_name=c["cluster"],
                score=c.get("score", 0.0),
                health_status=c.get("status", "unknown"),
                cpu_utilization=cpu_pct / 100.0 if cpu_pct is not None else None,
                gpu_available=c.get("gpu_available"),
                active_sandboxes=c.get("sandbox_active", 0),
                vm_density=c.get("vms_per_node"),
                hot_nodes=c.get("hot_nodes", 0),
                health_rate=c.get("health_rate"),
            )

        self._capacity_cache = new_cache
        self._cache_updated_at = datetime.utcnow()
        logger.info("Refreshed capacity cache: %d clusters", len(new_cache))
        return len(new_cache)

    def get_capacity_snapshot(self) -> List[ClusterCapacity]:
        return list(self._capacity_cache.values())

    def _cache_is_valid(self) -> bool:
        if not self._capacity_cache or not self._cache_updated_at:
            return False
        age = (datetime.utcnow() - self._cache_updated_at).total_seconds()
        return age < self.cache_ttl_seconds
