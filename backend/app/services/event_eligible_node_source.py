"""Read-only, fail-closed eligible-node inventory for an exact catalog release.

The placement policy must come from a trusted promoted release, never an order
body or an unversioned catalog edit. This adapter does not change cluster state.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.event_artifact_requirements import (
    ArtifactRequirementSourceError,
    TrustedEligibleNodes,
)


class NodeExpression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    operator: Literal["In", "NotIn", "Exists", "DoesNotExist", "Gt", "Lt"]
    values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_values(self) -> NodeExpression:
        if self.operator in {"In", "NotIn"} and not self.values:
            raise ValueError("set-based node expressions require values")
        if self.operator in {"Exists", "DoesNotExist"} and self.values:
            raise ValueError("existence node expressions cannot have values")
        if self.operator in {"Gt", "Lt"} and (
            len(self.values) != 1 or not self.values[0].isdigit()
        ):
            raise ValueError("numeric node expressions require one integer")
        return self


class NodeAffinityTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_expressions: list[NodeExpression] = Field(min_length=1)


class WorkloadToleration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = ""
    operator: Literal["Equal", "Exists"] = "Equal"
    value: str = ""
    effect: Literal["", "NoSchedule", "NoExecute", "PreferNoSchedule"] = ""
    toleration_seconds: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_toleration(self) -> WorkloadToleration:
        if self.operator == "Exists" and self.value:
            raise ValueError("Exists toleration cannot specify a value")
        if self.operator == "Equal" and not self.key:
            raise ValueError("Equal toleration requires a key")
        if self.toleration_seconds is not None:
            # A finite NoExecute allowance cannot prove durable placement.
            raise ValueError("finite tolerations cannot certify placement")
        return self


class TrustedWorkloadPlacement(BaseModel):
    """Scheduler-relevant policy from a promoted, immutable release."""

    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(min_length=1)
    catalog_release: str = Field(min_length=1)
    architecture: str = Field(min_length=1)
    node_selector: dict[str, str] = Field(default_factory=dict)
    # Kubernetes required affinity terms are ORed; expressions within a term
    # are ANDed. Empty terms cannot certify any node and are rejected.
    required_affinity_terms: list[NodeAffinityTerm] = Field(default_factory=list)
    tolerations: list[WorkloadToleration] = Field(default_factory=list)
    min_ready_seconds: int = Field(default=0, ge=0)


class TrustedPlacementSource(Protocol):
    def get_placement(
        self, catalog_id: str, catalog_release: str
    ) -> TrustedWorkloadPlacement | None: ...


def _match_expression(expression: NodeExpression, labels: dict[str, str]) -> bool:
    value = labels.get(expression.key)
    if expression.operator == "Exists":
        return value is not None
    if expression.operator == "DoesNotExist":
        return value is None
    if expression.operator == "NotIn" and value is None:
        # Kubernetes treats a missing key as satisfying NotIn.
        return True
    if value is None:
        return False
    if expression.operator == "In":
        return value in expression.values
    if expression.operator == "NotIn":
        return value not in expression.values
    if not value.isdigit():
        return False
    threshold = int(expression.values[0])
    return int(value) > threshold if expression.operator == "Gt" else int(value) < threshold


def _tolerates(taint: object, tolerations: list[WorkloadToleration]) -> bool:
    effect = str(getattr(taint, "effect", ""))
    if effect not in {"NoSchedule", "NoExecute"}:
        return True
    key = str(getattr(taint, "key", ""))
    value = str(getattr(taint, "value", "") or "")
    return any(
        (not tolerance.effect or tolerance.effect == effect)
        and (not tolerance.key or tolerance.key == key)
        and (tolerance.operator == "Exists" or (tolerance.key == key and tolerance.value == value))
        for tolerance in tolerations
    )


def _eligible(node: object, policy: TrustedWorkloadPlacement, observed_at: datetime) -> bool:
    metadata = getattr(node, "metadata", None)
    spec = getattr(node, "spec", None)
    status = getattr(node, "status", None)
    labels = getattr(metadata, "labels", None) or {}
    if not isinstance(labels, dict) or not spec or not status:
        return False
    if getattr(spec, "unschedulable", False):
        return False
    if any(
        role in labels
        for role in ("node-role.kubernetes.io/control-plane", "node-role.kubernetes.io/master")
    ):
        return False
    architecture = labels.get("kubernetes.io/arch")
    node_info = getattr(status, "node_info", None)
    if (
        architecture != policy.architecture
        or getattr(node_info, "architecture", None) != architecture
    ):
        return False
    if any(labels.get(key) != value for key, value in policy.node_selector.items()):
        return False
    if policy.required_affinity_terms and not any(
        all(_match_expression(expression, labels) for expression in term.match_expressions)
        for term in policy.required_affinity_terms
    ):
        return False
    if any(
        not _tolerates(taint, policy.tolerations) for taint in (getattr(spec, "taints", None) or [])
    ):
        return False
    conditions = {
        str(getattr(condition, "type", "")): condition
        for condition in (getattr(status, "conditions", None) or [])
    }
    ready = conditions.get("Ready")
    if ready is None or str(getattr(ready, "status", "")) != "True":
        return False
    if any(
        str(getattr(conditions.get(kind), "status", "False")) == "True"
        for kind in ("MemoryPressure", "DiskPressure", "PIDPressure")
    ):
        return False
    transition = getattr(ready, "last_transition_time", None)
    if policy.min_ready_seconds:
        if transition is None or transition.tzinfo is None:
            return False
        age = (observed_at - transition).total_seconds()
        if age < policy.min_ready_seconds or age < 0:
            return False
    return True


class KubernetesEligibleNodeSource:
    """Uses the persisted cluster identity and authenticated Kubernetes client."""

    def __init__(
        self,
        registry: object,
        client_factory: object,
        placements: TrustedPlacementSource,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.registry = registry
        self.client_factory = client_factory
        self.placements = placements
        self.clock = clock

    def get_eligible_nodes(
        self, cluster_id: str, catalog_id: str, catalog_release: str
    ) -> TrustedEligibleNodes:
        label = f"{cluster_id}/{catalog_id}@{catalog_release}"
        try:
            self.registry.get(cluster_id)  # Disabled/unknown targets fail closed.
            raw_policy = self.placements.get_placement(catalog_id, catalog_release)
            if raw_policy is None:
                raise ArtifactRequirementSourceError(f"trusted placement policy missing: {label}")
            policy = TrustedWorkloadPlacement.model_validate(raw_policy.model_dump())
            if (policy.catalog_id, policy.catalog_release) != (catalog_id, catalog_release):
                raise ArtifactRequirementSourceError(
                    f"placement release identity mismatches: {label}"
                )
            response = self.client_factory.clients(cluster_id).core.list_node(_request_timeout=10)
            metadata = getattr(response, "metadata", None)
            if not getattr(metadata, "resource_version", None) or (
                getattr(metadata, "_continue", None) or getattr(metadata, "continue_", None)
            ):
                raise ArtifactRequirementSourceError(f"node inventory is incomplete: {label}")
            nodes = getattr(response, "items", None)
            if not isinstance(nodes, list):
                raise ArtifactRequirementSourceError(f"node inventory is invalid: {label}")
            observed_at = self.clock()
            if observed_at.tzinfo is None:
                raise ArtifactRequirementSourceError("node observation time must include timezone")
            names = [
                str(node.metadata.name) for node in nodes if _eligible(node, policy, observed_at)
            ]
            if (
                not names
                or len(names) != len(set(names))
                or any(not name.strip() for name in names)
            ):
                raise ArtifactRequirementSourceError(f"no exact eligible node set: {label}")
            return TrustedEligibleNodes(
                cluster_id=cluster_id,
                catalog_id=catalog_id,
                catalog_release=catalog_release,
                node_ids=sorted(names),
                observed_at=observed_at,
            )
        except ArtifactRequirementSourceError:
            raise
        except Exception as exc:
            raise ArtifactRequirementSourceError(
                f"unable to resolve authenticated eligible nodes: {label}"
            ) from exc
