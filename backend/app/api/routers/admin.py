from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import catalog_adapter, provisioning_service
from app.auth.oauth import require_admin
from app.domain.enums import CatalogStatus
from app.domain.models import CatalogItem, LabSession
from app.integrations.llm_audit import get_llm_audit_log
from app.services.admin_observability import build_admin_observability
from app.services.health import check_health_detailed
from app.services.model_inventory import get_model_inventory
from app.services.resource_reconciliation import reconcile_resources
from app.services.system_monitor import SystemMonitor

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
monitor = SystemMonitor()


@router.get("/observability")
def admin_observability() -> Dict[str, Any]:
    """Return the read-only workflow view used by Launchpad Operations.

    This endpoint reports order/seat lifecycle state. Prometheus and Grafana
    remain the source of truth for historical resource and network telemetry.
    """

    catalog_names = {
        item.catalog_item_id: item.display_name
        for item in catalog_adapter.list_items()
    }
    try:
        inventory = get_model_inventory()
    except Exception:  # noqa: BLE001 - inventory degrades independently of workflow state
        inventory = {"summary": {}, "models": []}
    return build_admin_observability(
        sessions=provisioning_service._sessions.values(),
        workshops=provisioning_service._workshops.values(),
        clusters=provisioning_service.get_cluster_fleet_health(),
        grafana_url=os.environ.get("GRAFANA_LAUNCHPAD_DASHBOARD_URL", ""),
        catalog_names=catalog_names,
        model_inventory=inventory,
        llm_events=get_llm_audit_log(),
    )


@router.get("/system/health")
def detailed_system_health() -> Dict[str, Any]:
    return check_health_detailed()


@router.get("/models")
def model_inventory() -> Dict[str, Any]:
    """Return the curated Oberon portfolio and its current operational state."""
    return get_model_inventory()


@router.post("/system/reconcile")
def reconcile_system_resources() -> Dict[str, Any]:
    return reconcile_resources(provisioning_service)


@router.get("/system/status")
def system_status() -> Dict[str, Any]:
    status = monitor.get_status()
    status["active_sessions"] = len([
        s for s in provisioning_service._sessions.values()
        if s.status.value in ("ready", "active", "provisioning", "validating")
    ])
    status["total_sessions"] = len(provisioning_service._sessions)
    return status


@router.get("/clusters/preflight")
def preflight_cluster_targets() -> Dict[str, Any]:
    """Inspect enabled and disabled targets without changing placement state."""
    return {
        "mutates_cluster": False,
        "clusters": provisioning_service.get_cluster_fleet_health(
            include_disabled=True
        ),
    }


@router.get("/system/containers")
def list_containers() -> List[Dict[str, Any]]:
    containers = monitor.list_containers()
    stats = monitor.get_container_stats()
    stats_map = {s["name"]: s for s in stats}
    for c in containers:
        s = stats_map.get(c["name"], {})
        c["cpu_percent"] = s.get("cpu_percent", "—")
        c["memory_usage"] = s.get("memory_usage", "—")
        c["memory_percent"] = s.get("memory_percent", "—")
    return containers


@router.get("/system/containers/{name}/logs")
def container_logs(name: str, lines: int = 100) -> Dict[str, Any]:
    result = monitor.get_container_logs(name, lines)
    if not result["success"]:
        raise HTTPException(404, f"Container {name} not found or not accessible")
    return result


@router.post("/system/containers/{name}/restart")
def restart_container(name: str) -> Dict[str, Any]:
    result = monitor.restart_container(name)
    if not result["success"]:
        raise HTTPException(400, result["message"])
    return result


@router.post("/sessions/{session_id}/force-reclaim", response_model=LabSession)
def force_reclaim(session_id: str):
    try:
        return provisioning_service.force_reclaim_session(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/catalog/{catalog_item_id}/force-reclaim")
def force_reclaim_catalog_sessions(catalog_item_id: str) -> Dict[str, Any]:
    """Force-reclaim all active and failed sessions for one catalog item."""
    return provisioning_service.force_reclaim_catalog_sessions(catalog_item_id)


@router.get("/sessions/{session_id}/diagnostics")
def session_diagnostics(session_id: str) -> Dict[str, Any]:
    session = provisioning_service.get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    containers = monitor.list_containers()
    namespace = session.namespace or ""
    session_containers = [c for c in containers if namespace in c["name"]]

    health_checks = []
    for url_field in ["lab_url", "dashboard_url"]:
        url = getattr(session, url_field, None)
        if url:
            try:
                import httpx
                resp = httpx.get(url, timeout=5)
                health_checks.append({"url": url, "status": resp.status_code, "healthy": resp.status_code == 200})
            except Exception as e:
                health_checks.append({"url": url, "status": 0, "healthy": False, "error": str(e)})

    return {
        "session_id": session_id,
        "session_status": session.status.value,
        "container_status": session_containers if session_containers else containers,
        "health_checks": health_checks,
    }


@router.post("/catalog", response_model=CatalogItem, status_code=201)
def add_catalog_item(item: CatalogItem):
    try:
        return catalog_adapter.add_item(item)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/catalog/{catalog_item_id}", response_model=CatalogItem)
def update_catalog_item(catalog_item_id: str, updates: Dict[str, Any]):
    try:
        return catalog_adapter.update_item(catalog_item_id, updates)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.patch("/catalog/{catalog_item_id}/status", response_model=CatalogItem)
def set_catalog_status(catalog_item_id: str, body: Dict[str, str]):
    status_str = body.get("status")
    if not status_str:
        raise HTTPException(400, "Missing 'status' field")
    try:
        status = CatalogStatus(status_str)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {status_str}")
    try:
        return catalog_adapter.set_status(catalog_item_id, status)
    except ValueError as e:
        raise HTTPException(404, str(e))
