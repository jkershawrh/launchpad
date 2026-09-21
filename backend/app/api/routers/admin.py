from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import catalog_adapter, lifecycle_job_store, provisioning_service
from app.auth.oauth import require_admin
from app.domain.enums import CatalogStatus
from app.domain.models import CatalogItem, LabSessionResponse
from app.integrations.llm_audit import get_llm_audit_log
from app.services.admin_observability import build_admin_observability
from app.services.health import check_health_detailed
from app.services.lifecycle_worker import build_lifecycle_admin_view
from app.services.model_inventory import get_model_inventory
from app.services.resource_reconciliation import reconcile_resources
from app.services.seat_resource_metrics import collect_seat_resource_metrics
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
    provisioning_service.refresh_persisted_state()
    sessions = list(provisioning_service._sessions.values())
    seat_metrics = {}
    if provisioning_service.cluster_client_factory:
        seat_metrics = collect_seat_resource_metrics(
            sessions,
            provisioning_service.cluster_client_factory,
        )
    return build_admin_observability(
        sessions=sessions,
        workshops=provisioning_service._workshops.values(),
        clusters=provisioning_service.get_cluster_fleet_health(),
        grafana_url=os.environ.get("GRAFANA_LAUNCHPAD_DASHBOARD_URL", ""),
        catalog_names=catalog_names,
        model_inventory=inventory,
        llm_events=get_llm_audit_log(),
        seat_metrics=seat_metrics,
    )


@router.get("/system/health")
def detailed_system_health() -> Dict[str, Any]:
    return check_health_detailed()


@router.get("/lifecycle")
def lifecycle_queue_health() -> Dict[str, Any]:
    return build_lifecycle_admin_view(
        lifecycle_job_store.list_all(),
        enabled=os.environ.get("LIFECYCLE_HA_ENABLED", "false").lower() == "true",
        serialize_workshop_provisioning=(
            os.environ.get("SERIALIZE_WORKSHOP_PROVISIONING", "true").lower()
            == "true"
        ),
    )


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
    sessions = provisioning_service.list_sessions()
    status["active_sessions"] = len([
        s for s in sessions
        if s.status.value in ("ready", "active", "provisioning", "validating")
    ])
    status["total_sessions"] = len(sessions)
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


@router.get("/system/containers/{name}/logs", status_code=403)
def container_logs(name: str, lines: int = 100) -> Dict[str, Any]:
    # Raw runtime output is unstructured and may contain credentials. Operators
    # use approved log tooling; this API must not relay the raw stream.
    raise HTTPException(403, "Raw container logs are not available through Launchpad")


@router.post("/system/containers/{name}/restart")
def restart_container(name: str) -> Dict[str, Any]:
    result = monitor.restart_container(name)
    if not result["success"]:
        raise HTTPException(400, "Container restart could not be completed")
    return result


@router.post("/sessions/{session_id}/force-reclaim", response_model=LabSessionResponse)
def force_reclaim(session_id: str):
    try:
        return provisioning_service.force_reclaim_session(session_id)
    except ValueError:
        raise HTTPException(404, "Session not found")


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
            except Exception:
                health_checks.append({"url": url, "status": 0, "healthy": False, "error": "Endpoint check failed"})

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
    except ValueError:
        raise HTTPException(409, "Catalog operation conflicts with current state")


@router.put("/catalog/{catalog_item_id}", response_model=CatalogItem)
def update_catalog_item(catalog_item_id: str, updates: Dict[str, Any]):
    try:
        return catalog_adapter.update_item(catalog_item_id, updates)
    except ValueError:
        raise HTTPException(404, "Catalog item not found")


@router.patch("/catalog/{catalog_item_id}/status", response_model=CatalogItem)
def set_catalog_status(catalog_item_id: str, body: Dict[str, str]):
    status_str = body.get("status")
    if not status_str:
        raise HTTPException(400, "Missing 'status' field")
    try:
        status = CatalogStatus(status_str)
    except ValueError:
        raise HTTPException(400, "Invalid catalog status")
    try:
        return catalog_adapter.set_status(catalog_item_id, status)
    except ValueError:
        raise HTTPException(404, "Catalog item not found")
