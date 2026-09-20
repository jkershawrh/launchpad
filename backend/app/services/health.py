from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict

import httpx

from app.integrations.openai_compat import openai_api_url

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
            checks["litellm"] = _check_litellm(
                litellm_base,
                os.environ.get("LITELLM_API_KEY", ""),
                os.environ.get("MAAS_HEALTH_CANARY_MODEL", ""),
            )

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


def _check_lifecycle_schema() -> Dict[str, Any]:
    try:
        from app.storage.database import get_database_url

        url = get_database_url()
        if not url:
            return {"status": "fail", "message": "DATABASE_URL not set"}
        import psycopg2

        conn = psycopg2.connect(url, connect_timeout=3)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.lifecycle_jobs')")
                table = cur.fetchone()[0]
        finally:
            conn.close()
        if table != "lifecycle_jobs":
            return {"status": "fail", "message": "lifecycle_jobs schema is missing"}
        return {"status": "pass"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}


def _check_durable_state_bindings(bindings=None) -> Dict[str, Any]:
    """Prove an HA process is wired to durable stores, not local fallbacks.

    A reachable database is necessary but insufficient: dependency wiring can
    still construct process-local services.  Readiness must reject that split
    state before the pod receives mutating traffic.
    """
    if bindings is None:
        from app.api import deps as bindings

    failures: list[str] = []

    def require_postgres(name: str, value: Any) -> None:
        store_type = type(value)
        if not (
            store_type.__module__.startswith("app.storage.")
            and store_type.__name__.startswith("Postgres")
        ):
            failures.append(name)

    stores = getattr(bindings, "db_stores", None)
    if stores is None:
        failures.append("database_store_bundle")
    else:
        for name in (
            "tenants",
            "requests",
            "sessions",
            "plans",
            "showback",
            "workshops",
            "access",
            "events",
            "event_reservations",
            "lifecycle_jobs",
        ):
            require_postgres(name, getattr(stores, name, None))

    provisioning = getattr(bindings, "provisioning_service", None)
    provisioning_stores = getattr(provisioning, "db", None)
    if provisioning_stores is None:
        failures.append("provisioning")
    else:
        for name in ("requests", "sessions", "plans", "showback", "workshops"):
            require_postgres(
                f"provisioning.{name}", getattr(provisioning_stores, name, None)
            )

    require_postgres(
        "tenant_store", getattr(getattr(bindings, "tenant_store", None), "_db", None)
    )
    require_postgres(
        "public_access",
        getattr(getattr(bindings, "public_access_service", None), "store", None),
    )
    require_postgres(
        "event_manifests",
        getattr(getattr(bindings, "event_manifest_store", None), "_db", None),
    )
    require_postgres(
        "event_reservations",
        getattr(getattr(bindings, "event_reservation_ledger", None), "_db", None),
    )
    require_postgres(
        "lifecycle_queue", getattr(bindings, "lifecycle_job_store", None)
    )

    if failures:
        return {
            "status": "fail",
            "message": "HA state is not fully bound to durable storage",
            "unbound": sorted(set(failures)),
        }
    return {"status": "pass"}


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


def _check_litellm(api_base: str, api_key: str = "", canary_model: str = "") -> Dict[str, Any]:
    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = httpx.get(
            openai_api_url(api_base, "models"), headers=headers, timeout=5
        )
        resp.raise_for_status()
        models = resp.json().get("data", [])
        if not models:
            return {"status": "fail", "message": "authenticated model list is empty"}
        result: Dict[str, Any] = {"status": "pass", "models_available": len(models)}
        if canary_model:
            canary = httpx.post(
                openai_api_url(api_base, "chat/completions"),
                headers=headers,
                json={
                    "model": canary_model,
                    "messages": [{"role": "user", "content": "Reply only: OK"}],
                    "max_tokens": 3,
                },
                timeout=15,
            )
            canary.raise_for_status()
            choices = canary.json().get("choices", [])
            if not choices:
                return {"status": "fail", "message": "inference canary returned no choices"}
            result["inference_canary"] = "pass"
            result["canary_model"] = canary_model
        return result
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
