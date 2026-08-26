from __future__ import annotations

from datetime import datetime
import os
from typing import Any

from app.domain.enums import SessionStatus
from app.domain.models import LifecycleEvent


ACTIVE_STATES = {
    SessionStatus.READY,
    SessionStatus.ACTIVE,
    SessionStatus.VALIDATING,
    SessionStatus.PROVISIONING,
    SessionStatus.RESETTING,
}


def _core_api():
    from kubernetes import client, config
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()
    return client.CoreV1Api()


def _namespace_exists(namespace: str) -> bool:
    from kubernetes.client.exceptions import ApiException
    try:
        _core_api().read_namespace(namespace)
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


def _managed_namespaces() -> list[str]:
    result = _core_api().list_namespace(
        label_selector="app.kubernetes.io/managed-by=launchpad"
    )
    return sorted(item.metadata.name for item in result.items)


def _database_available() -> bool:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return True
    try:
        import psycopg2
        connection = psycopg2.connect(url, connect_timeout=3)
        connection.close()
        return True
    except Exception:
        return False


def reconcile_resources(service: Any, *, delete_orphans: bool = True) -> dict[str, Any]:
    """Reconcile persisted lifecycle state with launchpad-managed namespaces."""
    report: dict[str, Any] = {
        "sessions_reconciled": 0,
        "orphan_namespaces_deleted": [],
        "errors": [],
    }
    if delete_orphans and not _database_available():
        report["errors"].append("database unavailable — orphan deletion skipped")
        return report
    for session in list(service._sessions.values()):
        if session.status != SessionStatus.CLEANUP_FAILED or not session.namespace:
            continue
        try:
            if _namespace_exists(session.namespace):
                continue
            event = LifecycleEvent(
                from_status=session.status,
                to_status=SessionStatus.RECLAIMED,
                reason="reconciled — namespace deletion confirmed",
            )
            updated = session.model_copy(update={
                "status": SessionStatus.RECLAIMED,
                "completed_at": datetime.utcnow(),
                "lifecycle_events": session.lifecycle_events + [event],
            })
            updated = service._scrub_credentials(updated)
            service._save_session(updated)
            report["sessions_reconciled"] += 1
        except Exception as exc:
            report["errors"].append(f"session {session.session_id}: {exc}")

    # Terminal records must never retain access credentials, including records
    # reclaimed by older versions of the service.
    for session in list(service._sessions.values()):
        if session.status != SessionStatus.RECLAIMED:
            continue
        if session.maas_api_key or any(
            key in session.resources for key in ("sa_token", "sandbox_data")
        ):
            service._save_session(service._scrub_credentials(session))

    if not delete_orphans or not service.cleanup:
        return report

    referenced = {
        session.namespace
        for session in service._sessions.values()
        if session.namespace
    }
    for namespace in _managed_namespaces():
        if namespace in referenced:
            continue
        try:
            service.cleanup.cleanup(namespace)
            report["orphan_namespaces_deleted"].append(namespace)
        except Exception as exc:
            report["errors"].append(f"namespace {namespace}: {exc}")
    return report
