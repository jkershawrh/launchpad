"""Read-only Kubernetes inventory adapter for future event-capacity evidence.

This adapter is deliberately not wired to the collector CLI or order admission.
It requires an explicit target-specific client and a separate complete model-slot
source; an empty or partial API response never becomes positive headroom.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Protocol

from kubernetes.utils.quantity import parse_quantity

from app.domain.clusters import ClusterTarget
from app.services.event_inflight_capacity_collector import (
    ClusterInventory,
    InflightCollectionBlocked,
    NamespaceInventory,
    PodRequest,
)

_MIB = Decimal(1024 * 1024)


@dataclass(frozen=True)
class ModelSlotObservation:
    cluster_id: str
    observed_at: datetime
    allocatable_slots: int
    complete: bool


class ModelSlotSource(Protocol):
    def observe_model_slots(self, target: ClusterTarget) -> ModelSlotObservation: ...


def _name(value: object, kind: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise InflightCollectionBlocked(f"{kind} inventory identity is incomplete")
    return value


def _quantity(value: object, scale: Decimal, kind: str, *, allocatable: bool = False) -> int:
    if value is None:
        return 0
    try:
        amount = Decimal(parse_quantity(str(value))) * scale
        if not amount.is_finite() or amount < 0:
            raise ValueError("negative or non-finite quantity")
        return int(amount.to_integral_value(rounding=ROUND_FLOOR if allocatable else ROUND_CEILING))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise InflightCollectionBlocked(f"{kind} accounting is incomplete") from exc


def _resources(requests: object) -> tuple[int, int]:
    if requests is None:
        requests = {}
    if not isinstance(requests, dict):
        raise InflightCollectionBlocked("pod resource requests are invalid")
    return (
        _quantity(requests.get("cpu"), Decimal(1000), "pod CPU"),
        _quantity(requests.get("memory"), Decimal(1) / _MIB, "pod memory"),
    )


def _container_request(container: object) -> tuple[int, int]:
    resources = getattr(container, "resources", None)
    return _resources(getattr(resources, "requests", None))


def _pod_request(pod: object) -> PodRequest | None:
    metadata = getattr(pod, "metadata", None)
    status = getattr(pod, "status", None)
    spec = getattr(pod, "spec", None)
    uid = _name(getattr(metadata, "uid", None), "pod")
    phase = getattr(status, "phase", None)
    if phase not in {"Pending", "Running", "Succeeded", "Failed", "Unknown"}:
        raise InflightCollectionBlocked("pod phase is incomplete")
    if phase in {"Succeeded", "Failed"}:
        return None
    containers = getattr(spec, "containers", None)
    if not isinstance(containers, list) or not containers:
        raise InflightCollectionBlocked("pod container inventory is incomplete")
    regular = [_container_request(container) for container in containers]
    sidecar_cpu = sidecar_memory = 0
    max_init_cpu = max_init_memory = 0
    for init in getattr(spec, "init_containers", None) or []:
        cpu, memory = _container_request(init)
        if getattr(init, "restart_policy", None) == "Always":
            sidecar_cpu += cpu
            sidecar_memory += memory
            max_init_cpu = max(max_init_cpu, sidecar_cpu)
            max_init_memory = max(max_init_memory, sidecar_memory)
        else:
            max_init_cpu = max(max_init_cpu, sidecar_cpu + cpu)
            max_init_memory = max(max_init_memory, sidecar_memory + memory)
    overhead_cpu, overhead_memory = _resources(getattr(spec, "overhead", None))
    return PodRequest(
        uid=uid,
        cpu_millicores=max(sum(item[0] for item in regular) + sidecar_cpu, max_init_cpu)
        + overhead_cpu,
        memory_mib=max(sum(item[1] for item in regular) + sidecar_memory, max_init_memory)
        + overhead_memory,
    )


def _list_all(method: Callable, kind: str) -> list[object]:
    items: list[object] = []
    seen_tokens: set[str] = set()
    token = ""
    version: str | None = None
    for _ in range(1000):
        arguments: dict[str, object] = {"limit": 500, "_request_timeout": 10}
        if token:
            arguments["_continue"] = token
        response = method(**arguments)
        metadata = getattr(response, "metadata", None)
        current_version = getattr(metadata, "resource_version", None)
        if not isinstance(current_version, str) or not current_version:
            raise InflightCollectionBlocked(f"{kind} list has no resource version")
        if version is not None and current_version != version:
            raise InflightCollectionBlocked(f"{kind} list changed during pagination")
        version = current_version
        page_items = getattr(response, "items", None)
        if not isinstance(page_items, list):
            raise InflightCollectionBlocked(f"{kind} list is incomplete")
        items.extend(page_items)
        token = getattr(metadata, "_continue", None) or getattr(metadata, "continue_", None) or ""
        if not token:
            return items
        if not isinstance(token, str) or token in seen_tokens:
            raise InflightCollectionBlocked(f"{kind} pagination is incomplete")
        seen_tokens.add(token)
    raise InflightCollectionBlocked(f"{kind} pagination exceeded safety bound")


def _schedulable_worker(node: object) -> bool:
    metadata = getattr(node, "metadata", None)
    labels = getattr(metadata, "labels", None)
    if labels is None:
        labels = {}
    spec = getattr(node, "spec", None)
    status = getattr(node, "status", None)
    if not isinstance(labels, dict) or spec is None or status is None:
        raise InflightCollectionBlocked("node inventory is incomplete")
    if getattr(spec, "unschedulable", False):
        return False
    if any(
        getattr(taint, "effect", None) in {"NoSchedule", "NoExecute"}
        for taint in (getattr(spec, "taints", None) or [])
    ):
        # Without a promoted workload toleration policy, dedicated nodes must
        # not enlarge generic event headroom.
        return False
    if any(
        role in labels
        for role in ("node-role.kubernetes.io/control-plane", "node-role.kubernetes.io/master")
    ):
        return False
    conditions = getattr(status, "conditions", None)
    if not isinstance(conditions, list):
        raise InflightCollectionBlocked("node conditions are incomplete")
    states = {getattr(item, "type", None): getattr(item, "status", None) for item in conditions}
    if states.get("Ready") != "True":
        return False
    return not any(
        states.get(kind) == "True" for kind in ("MemoryPressure", "DiskPressure", "PIDPressure")
    )


class KubernetesClusterInventoryObserver:
    """Collect one exact target; no ambient context or cross-cluster fallback."""

    def __init__(
        self,
        client_factory: object,
        model_slots: ModelSlotSource,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.client_factory = client_factory
        self.model_slots = model_slots
        self.clock = clock

    def observe(self, target: ClusterTarget) -> ClusterInventory:
        if not target.enabled:
            raise InflightCollectionBlocked("disabled target cannot provide capacity evidence")
        try:
            core = self.client_factory.clients(target.cluster_id).core
            nodes = _list_all(core.list_node, "node")
            first_namespaces = _list_all(core.list_namespace, "namespace")
            pods = _list_all(core.list_pod_for_all_namespaces, "pod")
            second_namespaces = _list_all(core.list_namespace, "namespace")
            slots = self.model_slots.observe_model_slots(target)
            observed_at = self.clock()
        except InflightCollectionBlocked:
            raise
        except Exception as exc:
            raise InflightCollectionBlocked(
                "authenticated read-only cluster inventory unavailable"
            ) from exc
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
            raise InflightCollectionBlocked("cluster observation time requires timezone")
        if (
            not isinstance(slots, ModelSlotObservation)
            or slots.cluster_id != target.cluster_id
            or not slots.complete
            or type(slots.allocatable_slots) is not int
            or slots.allocatable_slots < 0
            or not isinstance(slots.observed_at, datetime)
            or slots.observed_at.tzinfo is None
            or not -30 <= (observed_at - slots.observed_at).total_seconds() <= 120
        ):
            raise InflightCollectionBlocked("model slot evidence is incomplete or stale")

        node_names: set[str] = set()
        cpu_total = memory_total = pods_total = 0
        for node in nodes:
            name = _name(getattr(getattr(node, "metadata", None), "name", None), "node")
            if name in node_names:
                raise InflightCollectionBlocked("duplicate node inventory identity")
            node_names.add(name)
            if not _schedulable_worker(node):
                continue
            allocatable = getattr(getattr(node, "status", None), "allocatable", None)
            if not isinstance(allocatable, dict) or not all(
                key in allocatable for key in ("cpu", "memory", "pods")
            ):
                raise InflightCollectionBlocked("node allocatable inventory is incomplete")
            cpu_total += _quantity(allocatable["cpu"], Decimal(1000), "node CPU", allocatable=True)
            memory_total += _quantity(
                allocatable["memory"], Decimal(1) / _MIB, "node memory", allocatable=True
            )
            pods_total += _quantity(allocatable["pods"], Decimal(1), "node pods", allocatable=True)
        if not node_names or pods_total == 0:
            raise InflightCollectionBlocked("no schedulable worker capacity observed")

        def namespace_index(rows: list[object]) -> dict[str, dict[str, str]]:
            result: dict[str, dict[str, str]] = {}
            for row in rows:
                metadata = getattr(row, "metadata", None)
                name = _name(getattr(metadata, "name", None), "namespace")
                labels = getattr(metadata, "labels", None)
                if labels is None:
                    labels = {}
                if name in result or not isinstance(labels, dict):
                    raise InflightCollectionBlocked("namespace inventory is duplicated or invalid")
                result[name] = labels
            return result

        names = namespace_index(first_namespaces)
        if names != namespace_index(second_namespaces):
            raise InflightCollectionBlocked("namespace inventory changed during observation")
        by_namespace: dict[str, list[PodRequest]] = {name: [] for name in names}
        seen_pods: set[str] = set()
        for pod in pods:
            metadata = getattr(pod, "metadata", None)
            namespace_name = _name(getattr(metadata, "namespace", None), "pod namespace")
            uid = _name(getattr(metadata, "uid", None), "pod")
            if namespace_name not in by_namespace or uid in seen_pods:
                raise InflightCollectionBlocked(
                    "pod inventory is duplicated or outside namespace roster"
                )
            seen_pods.add(uid)
            request = _pod_request(pod)
            if request is not None:
                by_namespace[namespace_name].append(request)
        return ClusterInventory(
            cluster_id=target.cluster_id,
            observed_at=observed_at,
            allocatable_cpu_millicores=cpu_total,
            allocatable_memory_mib=memory_total,
            allocatable_pods=pods_total,
            allocatable_model_slots=slots.allocatable_slots,
            namespace_names=tuple(sorted(names)),
            namespaces=tuple(
                NamespaceInventory(name=name, labels=names[name], pods=tuple(by_namespace[name]))
                for name in sorted(names)
            ),
            node_inventory_complete=True,
            namespace_inventory_complete=True,
            pod_inventory_complete=True,
            request_inventory_complete=True,
            model_slot_inventory_complete=True,
        )
