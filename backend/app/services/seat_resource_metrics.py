"""Best-effort live resource signals for active Launchpad seat namespaces."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


def _cpu_millicores(value: str) -> int:
    text = str(value or "0")
    if text.endswith("n"):
        return round(Decimal(text[:-1]) / Decimal(1_000_000))
    if text.endswith("u"):
        return round(Decimal(text[:-1]) / Decimal(1_000))
    if text.endswith("m"):
        return round(Decimal(text[:-1]))
    return round(Decimal(text) * Decimal(1_000))


def _memory_mib(value: str) -> int:
    text = str(value or "0")
    binary = {"Ki": Decimal(1) / 1024, "Mi": Decimal(1), "Gi": Decimal(1024), "Ti": Decimal(1024 * 1024)}
    decimal = {"K": Decimal(1_000) / Decimal(1024**2), "M": Decimal(1_000_000) / Decimal(1024**2), "G": Decimal(1_000_000_000) / Decimal(1024**2)}
    for suffix, multiplier in binary.items():
        if text.endswith(suffix):
            return round(Decimal(text[:-len(suffix)]) * multiplier)
    for suffix, multiplier in decimal.items():
        if text.endswith(suffix):
            return round(Decimal(text[:-len(suffix)]) * multiplier)
    return round(Decimal(text) / Decimal(1024**2))


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "cpu_millicores": None,
        "memory_mib": None,
        "pod_count": None,
        "ready_pods": None,
        "restarts": None,
        "terminal_reconnects": None,
        "observed_at": None,
    }


def collect_seat_resource_metrics(sessions: Iterable[Any], client_factory: Any) -> dict[str, dict[str, Any]]:
    """Aggregate Metrics API usage and pod health without failing the admin view."""

    session_list = [session for session in sessions if session.cluster_ref and session.namespace]
    result = {session.session_id: _unavailable("metrics not collected") for session in session_list}
    sessions_by_cluster: dict[str, list[Any]] = defaultdict(list)
    for session in session_list:
        sessions_by_cluster[session.cluster_ref].append(session)

    for cluster_ref, cluster_sessions in sessions_by_cluster.items():
        try:
            clients = client_factory.clients(cluster_ref, allow_disabled=True)
            metric_items = clients.custom.list_cluster_custom_object(
                group="metrics.k8s.io", version="v1beta1", plural="pods"
            ).get("items", [])
            pods = clients.core.list_pod_for_all_namespaces().items
        except Exception:  # noqa: BLE001 - one remote cluster must not break the fleet view
            for session in cluster_sessions:
                result[session.session_id] = _unavailable("cluster metrics unavailable")
            continue

        metric_by_namespace: dict[str, dict[str, int]] = defaultdict(lambda: {"cpu": 0, "memory": 0})
        for item in metric_items:
            namespace = (item.get("metadata") or {}).get("namespace")
            if not namespace:
                continue
            for container in item.get("containers", []):
                usage = container.get("usage", {})
                metric_by_namespace[namespace]["cpu"] += _cpu_millicores(usage.get("cpu", "0"))
                metric_by_namespace[namespace]["memory"] += _memory_mib(usage.get("memory", "0"))

        pod_by_namespace: dict[str, dict[str, int]] = defaultdict(lambda: {"pods": 0, "ready": 0, "restarts": 0})
        for pod in pods:
            namespace = getattr(pod.metadata, "namespace", None)
            if not namespace:
                continue
            statuses = getattr(pod.status, "container_statuses", None) or []
            pod_by_namespace[namespace]["pods"] += 1
            pod_by_namespace[namespace]["ready"] += int(bool(statuses) and all(status.ready for status in statuses))
            pod_by_namespace[namespace]["restarts"] += sum(int(status.restart_count or 0) for status in statuses)

        observed_at = datetime.now(UTC).isoformat()
        for session in cluster_sessions:
            usage = metric_by_namespace.get(session.namespace, {"cpu": 0, "memory": 0})
            health = pod_by_namespace.get(session.namespace, {"pods": 0, "ready": 0, "restarts": 0})
            result[session.session_id] = {
                "available": True,
                "cpu_millicores": usage["cpu"],
                "memory_mib": usage["memory"],
                "pod_count": health["pods"],
                "ready_pods": health["ready"],
                "restarts": health["restarts"],
                "terminal_reconnects": None,
                "observed_at": observed_at,
            }
    return result
