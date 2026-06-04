"""Fleet enrichment — pull deeper operational data from StarGate and DeepField.

Read-only. Cached locally. Polled every 5 minutes (not per-request).
Falls back silently if sources are unreachable.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("launchpad.fleet_enrichment")

CACHE_TTL = 300


class FleetEnrichment:

    def __init__(
        self,
        stargate_url: Optional[str] = None,
        stargate_api_key: Optional[str] = None,
        deepfield_url: Optional[str] = None,
    ):
        self.stargate_url = stargate_url or os.environ.get("STARGATE_API_URL", "")
        self.stargate_api_key = stargate_api_key or os.environ.get("STARGATE_API_KEY", "")
        self.deepfield_url = deepfield_url or os.environ.get("DEEPFIELD_API_URL", "")
        self._failure_classes: Dict[str, int] = {}
        self._cluster_observatory: Dict[str, Dict] = {}
        self._incidents: List[Dict] = []
        self._signals: List[Dict] = []
        self._provisioning_stats: Dict[str, Any] = {}
        self._pool_summary: List[Dict] = []
        self._last_refresh: float = 0

    def refresh(self) -> Dict[str, int]:
        counts = {}
        counts["failure_classes"] = self._pull_failure_classes()
        counts["cluster_observatory"] = self._pull_cluster_observatory()
        counts["incidents"] = self._pull_incidents()
        counts["signals"] = self._pull_signals()
        counts["provisioning"] = self._pull_provisioning_stats()
        counts["pools"] = self._pull_pool_summary()
        self._last_refresh = time.time()
        logger.info("Fleet enrichment refreshed: %s", counts)
        return counts

    def is_stale(self) -> bool:
        return time.time() - self._last_refresh > CACHE_TTL

    def get_failure_classes(self) -> Dict[str, int]:
        return dict(self._failure_classes)

    def get_cluster_observatory(self) -> Dict[str, Dict]:
        return dict(self._cluster_observatory)

    def get_incidents(self) -> List[Dict]:
        return list(self._incidents)

    def get_signals(self) -> List[Dict]:
        return list(self._signals)

    def get_provisioning_stats(self) -> Dict[str, Any]:
        return dict(self._provisioning_stats)

    def get_pool_summary(self) -> List[Dict]:
        return list(self._pool_summary)

    def get_summary(self) -> Dict[str, Any]:
        return {
            "failure_classes": len(self._failure_classes),
            "top_failure": max(self._failure_classes, key=self._failure_classes.get) if self._failure_classes else None,
            "clusters_observed": len(self._cluster_observatory),
            "open_incidents": len([i for i in self._incidents if i.get("status") == "open"]),
            "active_signals": len(self._signals),
            "total_provisions": self._provisioning_stats.get("total", 0),
            "provision_failure_rate": self._provisioning_stats.get("failure_rate", 0),
            "pools_available": len([p for p in self._pool_summary if p.get("available", 0) > 0]),
            "pools_exhausted": len([p for p in self._pool_summary if p.get("available", 0) == 0 and p.get("total", 0) > 0]),
            "last_refresh": self._last_refresh,
        }

    def _pull_failure_classes(self) -> int:
        if not self.stargate_url:
            return 0
        try:
            headers = {"X-API-Key": self.stargate_api_key} if self.stargate_api_key else {}
            resp = httpx.get(f"{self.stargate_url}/api/failure-classes", timeout=10, verify=False, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            classes = data if isinstance(data, list) else data.get("failure_classes", [])
            self._failure_classes = {}
            for fc in classes:
                if isinstance(fc, dict):
                    name = fc.get("name", fc.get("class_name", "unknown"))
                    count = fc.get("count", fc.get("total", 0))
                    self._failure_classes[name] = count
            return len(self._failure_classes)
        except Exception as e:
            logger.debug("Failed to pull failure classes: %s", e)
            return 0

    def _pull_cluster_observatory(self) -> int:
        if not self.deepfield_url:
            return 0
        try:
            resp = httpx.get(f"{self.deepfield_url}/api/v1/observatory/clusters", timeout=10, verify=False)
            resp.raise_for_status()
            data = resp.json()
            clusters = data.get("clusters", data) if isinstance(data, dict) else {}
            self._cluster_observatory = {}
            for name, info in clusters.items():
                if isinstance(info, dict):
                    self._cluster_observatory[name] = {
                        "total_pods": info.get("total_pods", 0),
                        "pods_running": info.get("pods_running", 0),
                        "pods_failed": info.get("pods_failed", 0),
                        "pods_crashloop": info.get("pods_crashloop", 0),
                        "total_nodes": info.get("total_nodes", 0),
                        "nodes_ready": info.get("nodes_ready", 0),
                        "warning_events": info.get("total_events_warning", 0),
                        "namespaces": len(info.get("namespaces", {})),
                        "last_scan": info.get("last_scan"),
                    }
            return len(self._cluster_observatory)
        except Exception as e:
            logger.debug("Failed to pull cluster observatory: %s", e)
            return 0

    def _pull_incidents(self) -> int:
        if not self.deepfield_url:
            return 0
        try:
            resp = httpx.get(f"{self.deepfield_url}/api/v1/incidents", timeout=10, verify=False)
            resp.raise_for_status()
            data = resp.json()
            incidents = data if isinstance(data, list) else data.get("incidents", [])
            self._incidents = [
                {
                    "id": i.get("id"),
                    "cluster": i.get("cluster_id"),
                    "namespace": i.get("namespace"),
                    "failure_class": i.get("failure_class"),
                    "severity": i.get("severity"),
                    "status": i.get("status"),
                    "signal_count": i.get("signal_count"),
                }
                for i in incidents[:50]
            ]
            return len(self._incidents)
        except Exception as e:
            logger.debug("Failed to pull incidents: %s", e)
            return 0

    def _pull_signals(self) -> int:
        if not self.deepfield_url:
            return 0
        try:
            resp = httpx.get(f"{self.deepfield_url}/api/v1/observatory/signals", timeout=10, verify=False)
            resp.raise_for_status()
            data = resp.json()
            signals = data.get("signals", []) if isinstance(data, dict) else []
            self._signals = [
                {
                    "type": s.get("signal_type"),
                    "namespace": s.get("namespace"),
                    "cluster": s.get("cluster"),
                    "severity": s.get("severity"),
                    "resource": s.get("resource_name"),
                }
                for s in signals[:50]
            ]
            return len(self._signals)
        except Exception as e:
            logger.debug("Failed to pull signals: %s", e)
            return 0

    def _pull_provisioning_stats(self) -> int:
        if not self.stargate_url:
            return 0
        try:
            headers = {"X-API-Key": self.stargate_api_key} if self.stargate_api_key else {}
            resp = httpx.get(f"{self.stargate_url}/dashboard/overview", timeout=10, verify=False, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            prov = data.get("provisioning", {})
            self._provisioning_stats = {
                "total": prov.get("total", 0),
                "started": prov.get("started", 0),
                "failed": prov.get("failed", 0),
                "failure_rate": prov.get("failure_rate", 0),
                "by_state": prov.get("by_state", {}),
            }
            pools = data.get("pools", {})
            pool_list = pools.get("all_pools", [])
            self._pool_summary = [
                {"name": p.get("name"), "available": p.get("available", 0), "total": p.get("total", 0)}
                for p in pool_list[:200]
                if isinstance(p, dict)
            ]
            return 1
        except Exception as e:
            logger.debug("Failed to pull provisioning stats: %s", e)
            return 0

    def _pull_pool_summary(self) -> int:
        return len(self._pool_summary)
