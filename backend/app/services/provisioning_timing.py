"""Provisioning timing — pull step-by-step timing from Babylon AnarchySubjects.

Read-only against Babylon. Cached. Runs on-demand or via Celery task.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("launchpad.provisioning_timing")

CACHE_TTL = 600


class ProvisioningTiming:

    def __init__(self, kubeconfig_path: Optional[str] = None):
        self._kubeconfig = kubeconfig_path or os.environ.get("BABYLON_KUBECONFIG", "")
        self._timings: List[Dict[str, Any]] = []
        self._last_refresh: float = 0

    def refresh(self) -> int:
        if not self._kubeconfig or not os.path.exists(self._kubeconfig):
            return 0

        namespaces = self._get_namespaces()
        all_timings = []

        cols = (
            "NAME:.metadata.name,"
            "CREATED:.metadata.creationTimestamp,"
            "START:.status.towerJobs.provision.startTimestamp,"
            "COMPLETE:.status.towerJobs.provision.completeTimestamp,"
            "JOB_STATUS:.status.towerJobs.provision.jobStatus"
        )

        for ns in namespaces:
            try:
                result = subprocess.run(
                    ["oc", "get", "anarchysubjects", "-n", ns, "--no-headers",
                     "-o", f"custom-columns={cols}"],
                    capture_output=True, text=True, timeout=30,
                    env={**os.environ, "KUBECONFIG": self._kubeconfig},
                )
                if result.returncode != 0:
                    continue
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) < 5:
                        continue
                    name, created, start, complete, status = parts[0], parts[1], parts[2], parts[3], parts[4]
                    if "<none>" in start or "<none>" in complete:
                        continue

                    try:
                        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        c = datetime.fromisoformat(complete.replace("Z", "+00:00"))
                        dur = (c - s).total_seconds()
                        if dur <= 0 or dur > 7200:
                            continue

                        catalog_parts = name.split(".")
                        catalog_item = ".".join(catalog_parts[:2]) if len(catalog_parts) >= 2 else name
                        stage = "prod"
                        if len(catalog_parts) >= 3:
                            sp = catalog_parts[2].split("-")[0]
                            if sp in ("prod", "dev", "event", "test"):
                                stage = sp

                        all_timings.append({
                            "name": name,
                            "catalog_item": catalog_item,
                            "stage": stage,
                            "created": created,
                            "start": start,
                            "complete": complete,
                            "duration_seconds": round(dur),
                            "duration_minutes": round(dur / 60, 1),
                            "status": status,
                        })
                    except Exception:
                        continue
            except Exception:
                continue

        self._timings = all_timings
        self._last_refresh = time.time()
        logger.info("Provisioning timing: %d records", len(all_timings))
        return len(all_timings)

    def is_stale(self) -> bool:
        return time.time() - self._last_refresh > CACHE_TTL

    def get_all(self) -> List[Dict]:
        return self._timings

    def get_stats(self) -> Dict[str, Any]:
        if not self._timings:
            return {}

        durations = sorted(t["duration_seconds"] for t in self._timings)
        n = len(durations)

        by_catalog: Dict[str, List[float]] = {}
        by_stage: Dict[str, List[float]] = {}
        for t in self._timings:
            by_catalog.setdefault(t["catalog_item"], []).append(t["duration_seconds"])
            by_stage.setdefault(t["stage"], []).append(t["duration_seconds"])

        catalog_avgs = [
            {"catalog_item": cat, "avg_minutes": round(sum(durs) / len(durs) / 60, 1),
             "count": len(durs), "min_minutes": round(min(durs) / 60, 1),
             "max_minutes": round(max(durs) / 60, 1)}
            for cat, durs in by_catalog.items() if len(durs) >= 2
        ]

        return {
            "total_provisions": n,
            "median_minutes": round(durations[n // 2] / 60, 1),
            "p90_minutes": round(durations[int(n * 0.9)] / 60, 1),
            "p99_minutes": round(durations[int(n * 0.99)] / 60, 1),
            "min_minutes": round(durations[0] / 60, 1),
            "max_minutes": round(durations[-1] / 60, 1),
            "by_stage": {
                stage: {"count": len(durs), "avg_minutes": round(sum(durs) / len(durs) / 60, 1)}
                for stage, durs in by_stage.items()
            },
            "slowest": sorted(catalog_avgs, key=lambda x: -x["avg_minutes"])[:10],
            "fastest": sorted(catalog_avgs, key=lambda x: x["avg_minutes"])[:10],
        }

    def _get_namespaces(self) -> List[str]:
        try:
            result = subprocess.run(
                ["oc", "get", "ns", "--no-headers", "-o", "custom-columns=NAME:.metadata.name"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "KUBECONFIG": self._kubeconfig},
            )
            if result.returncode != 0:
                return []
            return [ns.strip() for ns in result.stdout.strip().split("\n")
                    if ns.strip().startswith("babylon-anarchy")]
        except Exception:
            return []
