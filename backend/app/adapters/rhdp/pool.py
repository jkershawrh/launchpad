from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from app.adapters.rhdp.sandbox_api import SandboxAPIClient, SandboxAPIError

logger = logging.getLogger(__name__)

SANDBOX_PLACEMENT_TIMEOUT = int(os.environ.get("SANDBOX_PLACEMENT_TIMEOUT", "300"))

HARDWARE_TO_CAPABILITIES = {
    "gaudi-endpoint": {"gaudi": "true"},
    "gaudi-direct": {"gaudi": "true"},
    "xeon-basic": {},
    "xeon6": {"xeon6": "true"},
    "mixed-overdrive": {"gaudi": "true"},
}


class RHDPPoolAdapter:
    """PoolAdapter that claims/releases namespaces via the RHDP Sandbox API."""

    def __init__(self, sandbox_api: SandboxAPIClient | None = None):
        self._api = sandbox_api or SandboxAPIClient()
        self._reservations: dict[str, str] = {}

    def check_capacity(self, hardware_profile: str, quota_profile: str) -> bool:
        return True

    def reserve(
        self, session_id: str, hardware_profile: str, quota_profile: str,
        preferred_cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        cloud_selector = self._build_cloud_selector(hardware_profile, preferred_cluster=preferred_cluster)

        resources = [{
            "kind": "OcpSandbox",
            "cloud_selector": cloud_selector,
        }]

        try:
            result = self._api.create_placement(
                service_uuid=session_id,
                resources=resources,
                annotations={"guid": session_id[:8], "env_type": "launchpad"},
            )
        except SandboxAPIError as e:
            logger.error("Sandbox API placement failed: %s", e)
            raise ValueError(f"Failed to reserve sandbox: {e.message}") from e

        result = self._api.wait_for_placement(session_id, timeout=SANDBOX_PLACEMENT_TIMEOUT)

        if not result.resources:
            raise ValueError("Placement succeeded but returned no resources")

        resource = result.resources[0]
        self._reservations[session_id] = result.service_uuid

        return {
            "placement_service_uuid": result.service_uuid,
            "sandbox_name": resource.name,
            "namespace": resource.namespace,
            "ingress_domain": resource.ingress_domain,
            "console_url": resource.console_url,
            "sa_token": resource.sa_token,
            "cluster_additional_vars": resource.cluster_additional_vars,
        }

    def release(self, session_id: str) -> bool:
        try:
            self._api.delete_placement(session_id)
            self._reservations.pop(session_id, None)
            return True
        except SandboxAPIError as e:
            logger.error("Failed to release placement %s: %s", session_id, e)
            return False

    def report_allocation(self) -> Dict[str, Any]:
        try:
            sandboxes = self._api.list_sandboxes()
            return {
                "total_sandboxes": len(sandboxes),
                "reservations": dict(self._reservations),
            }
        except SandboxAPIError:
            return {"total_sandboxes": 0, "reservations": dict(self._reservations)}

    def _build_cloud_selector(
        self, hardware_profile: str, preferred_cluster: Optional[str] = None,
    ) -> Dict[str, str]:
        selector: dict[str, str] = {}
        caps = HARDWARE_TO_CAPABILITIES.get(hardware_profile, {})
        selector.update(caps)
        if preferred_cluster:
            selector["cluster_name"] = preferred_cluster
        return selector
