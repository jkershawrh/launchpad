"""TARSy result handler — processes investigation results from TARSy.

When TARSy completes an investigation for a provisioning failure, this
handler logs the result and publishes a lifecycle event so the rest of
the platform can react.

All operations fail silently — this is a best-effort integration.
"""

import logging
from typing import Any

logger = logging.getLogger("launchpad.tarsy")


def handle_tarsy_result(message: dict) -> None:
    """Process TARSy investigation results for provisioning failures.

    Expects an EcosystemEvent envelope with at least:
    - payload.alert_type
    - payload.originator_id (session_id)
    - payload.result
    """
    try:
        payload = message.get("payload", message)
        alert_type = payload.get("alert_type", "unknown")
        session_id = payload.get("originator_id", "unknown")
        result = payload.get("result", {})

        logger.info(
            "TARSy investigation completed for session %s (alert_type=%s): %s",
            session_id,
            alert_type,
            result.get("summary", "no summary"),
        )

        # Publish lifecycle event for observability
        _publish_lifecycle_event(session_id, payload)

    except Exception as e:
        logger.debug("TARSy result handling failed (non-critical): %s", e)


def _publish_lifecycle_event(session_id: str, payload: dict) -> None:
    """Publish a lifecycle event for the completed investigation."""
    try:
        from app.integrations.event_publisher import publish_event

        publish_event(
            session_id=session_id,
            namespace="",
            status="tarsy_investigation_completed",
            error_summary=payload.get("result", {}).get("summary", ""),
        )
    except Exception as e:
        logger.debug("Lifecycle event publish failed (non-critical): %s", e)
