"""StarGate capacity adapter — ask StarGate which cluster to provision on.

Calls StarGate's provisioning intelligence API to get cluster capacity
scores, then returns the best cluster for a new placement based on
CPU utilization, VM density, health rate, and pool availability.
"""

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
            resp = await client.get(f"{STARGATE_API_URL}/api/v1/clusters/capacity", headers=headers)
            resp.raise_for_status()
            return resp.json().get("clusters", [])
    except Exception as e:
        logger.debug(f"StarGate capacity check failed (non-critical): {e}")
        return []


async def get_best_cluster(
    requirements: Optional[Dict[str, Any]] = None,
    exclude_clusters: Optional[List[str]] = None,
) -> Optional[str]:
    """Return the cluster name with the highest capacity score.

    Optionally filter by requirements (e.g., min_cpu_available, gpu_required)
    and exclude specific clusters.
    """
    clusters = await get_cluster_capacity()
    if not clusters:
        return None

    if exclude_clusters:
        clusters = [c for c in clusters if c["cluster"] not in exclude_clusters]

    if requirements:
        min_score = requirements.get("min_score", 0)
        clusters = [c for c in clusters if c.get("score", 0) >= min_score]

        if requirements.get("healthy_only"):
            clusters = [c for c in clusters if c.get("status") == "healthy"]

    if not clusters:
        return None

    clusters.sort(key=lambda c: -c.get("score", 0))
    best = clusters[0]
    logger.info(f"StarGate recommends cluster '{best['cluster']}' (score: {best['score']})")
    return best["cluster"]


async def is_cluster_healthy(cluster_name: str) -> bool:
    """Quick health check for a specific cluster via StarGate."""
    if not STARGATE_API_URL:
        return True
    try:
        headers = {}
        if STARGATE_API_KEY:
            headers["X-API-Key"] = STARGATE_API_KEY
        async with httpx.AsyncClient(verify=STARGATE_SSL_VERIFY, timeout=5) as client:
            resp = await client.get(f"{STARGATE_API_URL}/api/v1/health/summary", headers=headers)
            resp.raise_for_status()
            clusters = resp.json().get("clusters", {})
            cluster = clusters.get(cluster_name, {})
            return cluster.get("healthy", True)
    except Exception as e:
        logger.debug(f"StarGate health check failed (assuming healthy): {e}")
        return True
