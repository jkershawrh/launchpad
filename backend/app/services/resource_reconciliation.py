from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.domain.enums import SessionStatus, WorkshopSeatStatus, WorkshopStatus
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


def _managed_namespaces(
    core=None, *, control_plane_id: str
) -> list[str]:
    result = (core or _core_api()).list_namespace(
        label_selector=(
            "app.kubernetes.io/managed-by=launchpad,"
            f"launchpad.redhat.com/control-plane-id={control_plane_id}"
        )
    )
    return sorted(
        item.metadata.name
        for item in result.items
        if item.metadata.name.startswith("launchpad-")
    )


def _namespace_metadata(
    namespace: str, core
) -> tuple[set[str], datetime | None]:
    item = core.read_namespace(namespace)
    labels = item.metadata.labels or {}
    owners = {
        value
        for value in (
            labels.get("launchpad.redhat.com/session-id"),
            labels.get("launchpad.redhat.com/request-id"),
        )
        if value
    }
    return owners, item.metadata.creation_timestamp


def _database_available() -> bool:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return False
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
        "workshops_reconciled": [],
        "late_workshop_sessions_reclaimed": [],
        "orphan_namespaces_deleted": [],
        "errors": [],
    }
    if delete_orphans and not _database_available():
        report["errors"].append("database unavailable — orphan deletion skipped")
        return report
    control_plane_id = os.environ.get("LAUNCHPAD_CONTROL_PLANE_ID", "").strip()
    if delete_orphans and not control_plane_id:
        report["errors"].append(
            "control-plane identity unavailable — orphan deletion skipped"
        )
        return report

    # A process that was replaced while provisioning can finish a seat after
    # another process has already completed the parent workshop reclaim. Such
    # a session is persisted and therefore is not a namespace orphan, but it
    # is invalid lifecycle state and must be reclaimed before orphan scanning.
    requests = getattr(service, "_requests", {})
    workshops = getattr(service, "_workshops", {})
    if (
        delete_orphans
        and isinstance(requests, dict)
        and isinstance(workshops, dict)
    ):
        terminal_workshop_states = {
            WorkshopStatus.COMPLETED,
            WorkshopStatus.COMPLETED_WITH_ERRORS,
        }
        for session in list(service._sessions.values()):
            if session.status not in ACTIVE_STATES:
                continue
            request = requests.get(session.request_id)
            workshop_id = (
                request.metadata.get("workshop_id") if request else None
            )
            workshop = workshops.get(workshop_id) if workshop_id else None
            if not workshop or workshop.status not in terminal_workshop_states:
                continue
            error = service._reclaim_workshop_session(session.session_id)
            if error:
                report["errors"].append(
                    f"completed workshop {workshop_id} session "
                    f"{session.session_id}: {error}"
                )
                continue
            report["late_workshop_sessions_reclaimed"].append(
                {
                    "workshop_id": workshop_id,
                    "session_id": session.session_id,
                    "cluster_id": session.cluster_ref,
                    "namespace": session.namespace,
                }
            )
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

    # TTL enforcement reclaims sessions independently. Repair the parent
    # aggregate only after every seat has a persisted, reclaimed session (or
    # was already marked reclaimed), so an interrupted or partially active
    # workshop can never be completed early.
    terminal_workshop_states = {
        WorkshopStatus.COMPLETED,
        WorkshopStatus.COMPLETED_WITH_ERRORS,
    }
    workshops = getattr(service, "_workshops", {})
    if isinstance(workshops, dict):
        for workshop in list(workshops.values()):
            if workshop.status in terminal_workshop_states or not workshop.seats:
                continue
            if workshop.status == WorkshopStatus.RECLAIMING:
                continue
            seat_sessions = {
                seat.session_id: service._sessions.get(seat.session_id)
                for seat in workshop.seats
                if seat.session_id
            }
            all_seats_reclaimed = all(
                (
                    seat.status == WorkshopSeatStatus.RECLAIMED
                    if not seat.session_id
                    else seat_sessions.get(seat.session_id) is not None
                    and seat_sessions[seat.session_id].status == SessionStatus.RECLAIMED
                )
                for seat in workshop.seats
            )
            if not all_seats_reclaimed:
                continue
            updated = workshop.model_copy(
                update={
                    "status": WorkshopStatus.COMPLETED,
                    "completed_at": datetime.utcnow(),
                    "seats": [
                        seat.model_copy(
                            update={
                                "status": WorkshopSeatStatus.RECLAIMED,
                                "error": None,
                                "updated_at": datetime.utcnow(),
                            }
                        )
                        for seat in workshop.seats
                    ],
                }
            )
            try:
                service._save_workshop(updated)
                access = getattr(service, "public_access_service", None)
                if access:
                    access.expire_order(workshop.workshop_id)
                report["workshops_reconciled"].append(
                    {
                        "workshop_id": workshop.workshop_id,
                        "cluster_id": workshop.cluster_ref,
                        "session_count": len(workshop.session_ids),
                    }
                )
            except Exception as exc:
                report["errors"].append(
                    f"workshop {workshop.workshop_id}: {exc}"
                )

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
            namespaces = _managed_namespaces(
                core, control_plane_id=control_plane_id
            )
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
                    owners, created_at = _namespace_metadata(namespace, core)
                    # A reconciliation process can hold a stale session
                    # snapshot while a new workshop creates namespaces. Never
                    # delete a recently created namespace solely because that
                    # snapshot does not reference it yet.
                    if created_at is not None:
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) - created_at < orphan_grace:
                            continue
                    if owners and any(
                        session.session_id in owners
                        or session.request_id in owners
                        or any(session.request_id.startswith(owner) for owner in owners)
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
