from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict

import httpx

logger = logging.getLogger("launchpad.health")

_start_time = time.monotonic()


def check_health_detailed() -> Dict[str, Any]:
    mode = os.environ.get("LAUNCHPAD_MODE", "mock")
    checks: Dict[str, Dict[str, Any]] = {}
    critical_fail = False

    if mode != "mock":
        checks["db"] = _check_db()
        if checks["db"]["status"] == "fail":
            critical_fail = True

        checks["k8s"] = _check_k8s()
        if checks["k8s"]["status"] == "fail":
            critical_fail = True

        litellm_base = os.environ.get("LITELLM_API_BASE", "")
        if litellm_base:
            checks["litellm"] = _check_litellm(litellm_base)

    checks["catalog"] = _check_catalog()
    checks["sessions"] = _check_sessions()

    if critical_fail:
        status = "unhealthy"
    elif any(c["status"] == "fail" for c in checks.values()):
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
    }


def _check_db() -> Dict[str, Any]:
    try:
        from app.storage.database import get_database_url
        url = get_database_url()
        if not url:
            return {"status": "skip", "message": "DATABASE_URL not set"}
        import psycopg2
        conn = psycopg2.connect(url, connect_timeout=3)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return {"status": "pass"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}


def _check_k8s() -> Dict[str, Any]:
    try:
        from kubernetes import client, config
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        v1 = client.CoreV1Api()
        v1.list_namespace(limit=1, _request_timeout=3)
        return {"status": "pass"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}


def _check_litellm(api_base: str) -> Dict[str, Any]:
    try:
        resp = httpx.get(f"{api_base.rstrip('/')}/health", timeout=3)
        if resp.status_code < 500:
            return {"status": "pass"}
        return {"status": "fail", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}


def _check_catalog() -> Dict[str, Any]:
    try:
        from app.api.deps import catalog_adapter
        items = catalog_adapter.list_items()
        from app.domain.enums import CatalogStatus
        active = sum(1 for i in items if i.status == CatalogStatus.ACTIVE)
        return {"status": "pass", "total": len(items), "active": active}
    except Exception as e:
        return {"status": "fail", "message": str(e)}


def _check_sessions() -> Dict[str, Any]:
    try:
        from app.api.deps import provisioning_service
        active = sum(
            1 for s in provisioning_service._sessions.values()
            if s.status.value in ("ready", "active", "provisioning", "validating")
        )
        return {"status": "pass", "active": active, "total": len(provisioning_service._sessions)}
    except Exception as e:
        return {"status": "fail", "message": str(e)}
