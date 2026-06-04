"""Data seeder — pull historical provisioning outcomes from Babylon and seed FeedbackTracker.

Read-only against Babylon. Runs once on demand or via Celery task.
Separates event (Summit) data from day-to-day operations.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional

from app.domain.feedback import ProvisioningOutcome

logger = logging.getLogger("launchpad.data_seeder")


class DataSeeder:

    def __init__(self, kubeconfig_path: Optional[str] = None):
        self._kubeconfig = kubeconfig_path or os.environ.get("BABYLON_KUBECONFIG", "")

    def seed_from_babylon(self) -> Dict[str, int]:
        if not self._kubeconfig or not os.path.exists(self._kubeconfig):
            return {"error": "no kubeconfig"}

        subjects = self._fetch_anarchy_subjects()
        if not subjects:
            return {"error": "no subjects found"}

        outcomes = self._parse_outcomes(subjects)

        event_outcomes = [o for o in outcomes if o.get("stage") == "event"]
        prod_outcomes = [o for o in outcomes if o.get("stage") == "prod"]
        dev_outcomes = [o for o in outcomes if o.get("stage") == "dev"]

        return {
            "total_subjects": len(subjects),
            "total_outcomes": len(outcomes),
            "prod": len(prod_outcomes),
            "event": len(event_outcomes),
            "dev": len(dev_outcomes),
            "success": sum(1 for o in outcomes if o["success"]),
            "failed": sum(1 for o in outcomes if o["failed"]),
            "catalog_items": len(set(o["catalog_item"] for o in outcomes)),
            "outcomes": outcomes,
        }

    def get_provisioning_outcomes(self) -> List[ProvisioningOutcome]:
        result = self.seed_from_babylon()
        if "error" in result:
            return []

        outcomes = []
        for raw in result.get("outcomes", []):
            outcomes.append(ProvisioningOutcome(
                session_id=raw["subject_name"],
                request_id=raw["subject_name"],
                catalog_item_id=raw["catalog_item"],
                cluster_name=raw.get("stage", "unknown"),
                hardware_profile="unknown",
                quota_profile="standard",
                workload_type=raw.get("category"),
                success=raw["success"],
                failure_reason=raw["state"] if raw["failed"] else None,
                provision_latency_ms=0,
                validation_passed=raw["success"],
                created_at=datetime.fromisoformat(raw["created"].replace("Z", "+00:00")) if raw.get("created") else datetime.utcnow(),
            ))
        return outcomes

    def _fetch_anarchy_subjects(self) -> List[Dict]:
        namespaces = self._get_anarchy_namespaces()
        if not namespaces:
            return []

        all_items = []
        cols = "NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp"
        for ns in namespaces:
            try:
                result = subprocess.run(
                    ["oc", "get", "anarchysubjects", "-n", ns, "--no-headers",
                     "-o", f"custom-columns={cols}"],
                    capture_output=True, text=True, timeout=30,
                    env={**os.environ, "KUBECONFIG": self._kubeconfig},
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if not line.strip():
                            continue
                        parts = line.split()
                        if len(parts) >= 3:
                            all_items.append({
                                "metadata": {"name": parts[0], "creationTimestamp": parts[2]},
                                "status": {"state": parts[1] if parts[1] != "<none>" else "unknown"},
                            })
            except Exception:
                continue
        return all_items

    def _get_anarchy_namespaces(self) -> List[str]:
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

    def _parse_outcomes(self, subjects: List[Dict]) -> List[Dict]:
        outcomes = []
        for item in subjects:
            meta = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})
            name = meta.get("name", "")
            state = status.get("state") or spec.get("vars", {}).get("current_state", "unknown")
            created = meta.get("creationTimestamp", "")

            parts = name.split(".")
            catalog_name = ".".join(parts[:2]) if len(parts) >= 2 else name
            category = parts[0] if parts else "unknown"

            stage = "prod"
            if len(parts) >= 3:
                stage_part = parts[2].split("-")[0]
                if stage_part in ("prod", "dev", "event", "test"):
                    stage = stage_part

            is_success = state in ("started", "stopped", "stopping", "stop-pending")
            is_failed = "fail" in state or "error" in state

            outcomes.append({
                "subject_name": name,
                "catalog_item": catalog_name,
                "category": category,
                "stage": stage,
                "state": state,
                "success": is_success,
                "failed": is_failed,
                "created": created,
            })

        return outcomes
