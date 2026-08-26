from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _namespace_exists(namespace: str, core=None) -> bool:
    from kubernetes.client.exceptions import ApiException
    try:
        (core or _core_api()).read_namespace(namespace)
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


def _managed_namespaces(core=None) -> list[str]:
    result = (core or _core_api()).list_namespace(
        label_selector="app.kubernetes.io/managed-by=launchpad"
    )
    return sorted(
        item.metadata.name
        for item in result.items
        if item.metadata.name.startswith("launchpad-")
    )


def _namespace_metadata(namespace: str, core) -> tuple[str | None, datetime | None]:
    item = core.read_namespace(namespace)
    labels = item.metadata.labels or {}
    return (
        labels.get("launchpad.redhat.com/session-id"),
        item.metadata.creation_timestamp,
    )


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
            core = (
                service._target_clients(session.cluster_ref).core
                if session.cluster_ref and getattr(service, "cluster_client_factory", None)
                else None
            )
            if _namespace_exists(session.namespace, core):
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

    from app.services.cluster_registry import ClusterRegistry
    registry = getattr(service, "cluster_registry", None)
    cluster_ids = (
        [target.cluster_id for target in registry.list_enabled()]
        if isinstance(registry, ClusterRegistry)
        else [None]
    )
    for cluster_id in cluster_ids:
        orphan_grace = timedelta(seconds=max(
            0, int(os.environ.get("ORPHAN_CLEANUP_GRACE_SECONDS", "1800"))
        ))
        referenced = {
            session.namespace
            for session in service._sessions.values()
            if session.namespace and session.cluster_ref == cluster_id
        } if cluster_id else {
            session.namespace for session in service._sessions.values() if session.namespace
        }
        try:
            core = service._target_clients(cluster_id).core if cluster_id else None
            namespaces = _managed_namespaces(core)
        except Exception as exc:
            report["errors"].append(f"cluster {cluster_id or 'local'}: {exc}")
            continue
        for namespace in namespaces:
            if namespace in referenced:
                continue
            # Provisioners persist a session before mutation, but the final
            # demo namespace can differ from the initial plan namespace. The
            # request label is therefore the authoritative ownership bridge
            # while provisioning is still in flight.
            if core is not None:
                try:
                    owner, created_at = _namespace_metadata(namespace, core)
                    # A reconciliation process can hold a stale session
                    # snapshot while a new workshop creates namespaces. Never
                    # delete a recently created namespace solely because that
                    # snapshot does not reference it yet.
                    if created_at is not None:
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) - created_at < orphan_grace:
                            continue
                    if owner and any(
                        session.request_id == owner
                        or session.request_id.startswith(owner)
                        for session in service._sessions.values()
                        if session.status in ACTIVE_STATES
                    ):
                        continue
                except Exception as exc:
                    report["errors"].append(
                        f"cluster {cluster_id} namespace {namespace} ownership: {exc}"
                    )
                    continue
            try:
                cleanup = service._get_cleanup(cluster_id) if cluster_id else service.cleanup
                cleanup.cleanup(namespace)
                report["orphan_namespaces_deleted"].append(
                    {"cluster_id": cluster_id, "namespace": namespace}
                    if cluster_id else namespace
                )
            except Exception as exc:
                report["errors"].append(
                    f"cluster {cluster_id or 'local'} namespace {namespace}: {exc}"
                )
    return report
