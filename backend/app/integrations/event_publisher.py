"""Multi-target event publisher for Launchpad lifecycle events.

Pushes lifecycle events to StarGate for external evidence tracking.
Graceful degradation: if StarGate URL is not configured, events are silently skipped.
If a push fails, it logs at debug level and continues.
"""

import json
import logging
import os
import ssl
import urllib.request
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger("launchpad.events")

STARGATE_API_URL = os.environ.get("STARGATE_API_URL", "")
STARGATE_API_KEY = os.environ.get("STARGATE_API_KEY", "")
STARGATE_SSL_VERIFY = os.environ.get("STARGATE_SSL_VERIFY", "true").lower() != "false"



def publish_event(
    session_id: str,
    namespace: str,
    status: str,
    lab_code: str = "",
    cluster_name: str = "",
    tenant_id: str = "",
    error_summary: str = "",
    resources: Optional[dict] = None,
) -> None:
    """Push a lifecycle event to all configured integration targets."""
    outcome = (
        "pass" if status in ("ready", "active")
        else "fail" if status in ("validation_failed", "expired")
        else "info"
    )

    payload = {
        "source": "launchpad",
        "event_type": f"session.{status}",
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "session_name": f"launchpad-{tenant_id}-{lab_code}",
        "lab_code": lab_code or namespace,
        "cluster_name": cluster_name or "local",
        "outcome": outcome,
        "error_summary": error_summary,
        "workshop_url": (resources or {}).get("lab_url", ""),
        "steps_passed": 1 if outcome == "pass" else 0,
        "steps_failed": 1 if outcome == "fail" else 0,
    }

    # Push to StarGate
    _push(
        STARGATE_API_URL, STARGATE_API_KEY, payload,
        endpoint="/integration/external-evidence",
        verify_ssl=STARGATE_SSL_VERIFY,
    )


def _push(
    base_url: str,
    api_key: str,
    payload: dict,
    endpoint: str = "/integration/events",
    verify_ssl: bool = True,
) -> None:
    """Push an event to a single target. Fails silently."""
    if not base_url:
        return
    try:
        ctx = ssl.create_default_context()
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key

        req = urllib.request.Request(
            f"{base_url}{endpoint}",
            data=data,
            headers=headers,
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10, context=ctx)
        logger.debug("Event pushed to %s: %s -> %s", base_url, payload.get("event_type"), resp.status)
    except Exception as e:
        logger.debug("Event push to %s failed (non-critical): %s", base_url, e)


# Backward-compatible alias: existing callers use notify_stargate()
notify_stargate = publish_event
