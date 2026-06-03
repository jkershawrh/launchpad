"""TARSy escalation trigger for repeated provisioning failures.

When a (catalog_item, cluster, hardware_profile) tuple drops below 30%
success rate after at least 3 attempts, we publish a TARSy investigation
request to Kafka.  A 30-minute cooldown prevents duplicate escalations.

All Kafka operations fail silently — this is a best-effort integration.
"""

import json
import logging
import time
from typing import Any

logger = logging.getLogger("launchpad.tarsy")

_escalation_cooldown: dict[str, float] = {}
COOLDOWN_SECONDS = 1800  # 30 minutes


def _cooldown_key(catalog_item_id: str, cluster_name: str, hardware_profile: str) -> str:
    return f"{catalog_item_id}:{cluster_name}:{hardware_profile}"


def check_tarsy_escalation(
    catalog_item_id: str,
    cluster_name: str,
    hardware_profile: str,
    success_rate: float,
    total_attempts: int,
) -> bool:
    """Check if this failure pattern should trigger TARSy investigation.

    Returns True when:
    - success_rate < 0.3
    - total_attempts >= 3
    - Not in cooldown (last escalation was > 30 min ago)
    """
    if success_rate >= 0.3:
        return False
    if total_attempts < 3:
        return False

    key = _cooldown_key(catalog_item_id, cluster_name, hardware_profile)
    if key in _escalation_cooldown:
        if time.monotonic() - _escalation_cooldown[key] < COOLDOWN_SECONDS:
            return False

    return True


def escalate_provision_failure(
    session_id: str,
    catalog_item_id: str,
    cluster_name: str,
    hardware_profile: str,
    error_summary: str,
    feedback_summary: dict,
) -> None:
    """Build and publish a TARSy investigation request for provisioning failure."""
    key = _cooldown_key(catalog_item_id, cluster_name, hardware_profile)

    request_dict = {
        "alert_type": "ProvisioningFailure",
        "severity": "medium",
        "originator_id": session_id,
        "data": json.dumps({
            "catalog_item_id": catalog_item_id,
            "cluster_name": cluster_name,
            "hardware_profile": hardware_profile,
            "error_summary": error_summary,
            "feedback_history": feedback_summary,
        }),
        "mcp_override": {
            "servers": [{
                "name": "kubernetes-server",
                "tools": [
                    "get_pods", "describe_pod", "get_events", "get_logs",
                    "get_nodes", "describe_node", "get_deployments", "get_services",
                ],
            }],
        },
    }

    try:
        from app.integrations.kafka_publisher import publish_tarsy_request
        publish_tarsy_request(request_dict)
        logger.info(
            "TARSy escalation published for %s on %s/%s",
            catalog_item_id, cluster_name, hardware_profile,
        )
    except Exception as e:
        logger.debug("TARSy escalation publish failed (non-critical): %s", e)

    _escalation_cooldown[key] = time.monotonic()
