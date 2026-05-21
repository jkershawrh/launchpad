"""StarGate integration — post lifecycle events as external evidence.

When STARGATE_API_URL is configured, Launchpad posts session lifecycle
events to StarGate's /integration/external-evidence endpoint on key
transitions (provisioned, validation passed/failed, active, reclaimed).

This lets StarGate monitor Launchpad labs as a live testbed for
auto-remediation without needing a separate collector.
"""

import json
import logging
import os
import ssl
import urllib.request
from typing import Optional

logger = logging.getLogger("launchpad.stargate")

STARGATE_API_URL = os.environ.get("STARGATE_API_URL", "")
STARGATE_API_KEY = os.environ.get("STARGATE_API_KEY", "")


def notify_stargate(
    session_id: str,
    namespace: str,
    status: str,
    lab_code: str = "",
    cluster_name: str = "",
    tenant_id: str = "",
    error_summary: str = "",
    resources: Optional[dict] = None,
) -> None:
    """Post a lifecycle event to StarGate as external evidence."""
    if not STARGATE_API_URL:
        return

    outcome = "pass" if status in ("ready", "active") else "fail" if status in ("validation_failed", "expired") else "info"

    payload = {
        "source": "launchpad",
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

    try:
        ctx = ssl.create_default_context()
        if os.environ.get("STARGATE_SSL_VERIFY", "true").lower() == "false":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if STARGATE_API_KEY:
            headers["X-API-Key"] = STARGATE_API_KEY

        req = urllib.request.Request(
            f"{STARGATE_API_URL}/integration/external-evidence",
            data=data,
            headers=headers,
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10, context=ctx)
        logger.debug(f"StarGate notified: {status} for {namespace} -> {resp.status}")
    except Exception as e:
        logger.debug(f"StarGate notification failed (non-critical): {e}")
