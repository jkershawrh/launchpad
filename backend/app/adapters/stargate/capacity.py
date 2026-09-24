"""StarGate capacity and health adapter for provider-neutral placement."""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("launchpad.stargate_capacity")

STARGATE_API_URL = os.environ.get("STARGATE_API_URL", "")
STARGATE_API_KEY = os.environ.get("STARGATE_API_KEY", "")
STARGATE_SSL_VERIFY = os.environ.get("STARGATE_SSL_VERIFY", "true").lower() != "false"


async def get_cluster_capacity() -> List[Dict[str, Any]]:
    """Fetch per-cluster capacity scores from StarGate."""
    if not STARGATE_API_URL:
        return []
    try:
        headers = {}
        if STARGATE_API_KEY:
            headers["X-API-Key"] = STARGATE_API_KEY
        async with httpx.AsyncClient(verify=STARGATE_SSL_VERIFY, timeout=10) as client:
            response = await client.get(
                f"{STARGATE_API_URL}/api/v1/clusters/capacity", headers=headers
            )
            response.raise_for_status()
            return response.json().get("clusters", [])
    except Exception as exc:  # noqa: BLE001 - placement degrades to local capacity
        logger.debug("StarGate capacity check failed (non-critical): %s", exc)
        return []


async def get_best_cluster(
    requirements: Optional[Dict[str, Any]] = None,
    exclude_clusters: Optional[List[str]] = None,
) -> Optional[str]:
    """Return the eligible cluster with the highest capacity score."""
    clusters = await get_cluster_capacity()
    if exclude_clusters:
        clusters = [item for item in clusters if item["cluster"] not in exclude_clusters]
    if requirements:
        clusters = [
            item
            for item in clusters
            if item.get("score", 0) >= requirements.get("min_score", 0)
            and (not requirements.get("healthy_only") or item.get("status") == "healthy")
        ]
    if not clusters:
        return None
    best = max(clusters, key=lambda item: item.get("score", 0))
    logger.info(
        "StarGate recommends cluster '%s' (score: %s)",
        best["cluster"],
        best.get("score", 0),
    )
    return best["cluster"]


async def is_cluster_healthy(cluster_name: str) -> bool:
    """Return StarGate health for one cluster, failing open when unavailable."""
    if not STARGATE_API_URL:
        return True
    try:
        headers = {}
        if STARGATE_API_KEY:
            headers["X-API-Key"] = STARGATE_API_KEY
        async with httpx.AsyncClient(verify=STARGATE_SSL_VERIFY, timeout=5) as client:
            response = await client.get(
                f"{STARGATE_API_URL}/api/v1/health/summary", headers=headers
            )
            response.raise_for_status()
            cluster = response.json().get("clusters", {}).get(cluster_name, {})
            return cluster.get("healthy", True)
    except Exception as exc:  # noqa: BLE001 - health is advisory for this adapter
        logger.debug("StarGate health check failed (assuming healthy): %s", exc)
        return True
