"""Read ACM placement decisions without inferring Launchpad capacity."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from app.domain.acm import AcmClusterObservation, AcmPlacementSnapshot

GROUP = "cluster.open-cluster-management.io"
PLACEMENT_VERSION = "v1beta1"


class AcmPlacementUnavailableError(RuntimeError):
    """The hub could not provide a trustworthy placement snapshot."""


class AcmPlacementAdapter:
    def __init__(self, custom_objects_api, *, namespace: str, placement_name: str) -> None:
        self.api = custom_objects_api
        self.namespace = namespace
        self.placement_name = placement_name

    def snapshot(self) -> AcmPlacementSnapshot:
        try:
            response = self.api.list_namespaced_custom_object(
                group=GROUP,
                version=PLACEMENT_VERSION,
                namespace=self.namespace,
                plural="placementdecisions",
                label_selector=(
                    "cluster.open-cluster-management.io/placement="
                    f"{self.placement_name}"
                ),
            )
            decisions = response.get("items") or []
            selected: dict[str, set[str]] = defaultdict(set)
            decision_versions: list[tuple[str, str]] = []
            for decision in decisions:
                metadata = decision.get("metadata") or {}
                decision_versions.append(
                    (metadata.get("name", ""), metadata.get("resourceVersion", ""))
                )
                for item in (decision.get("status") or {}).get("decisions") or []:
                    cluster_id = item.get("clusterName", "").strip()
                    if cluster_id:
                        selected[cluster_id].add(item.get("reason", "").strip())

            observations = [
                self._observe_cluster(cluster_id, sorted(selected[cluster_id]))
                for cluster_id in sorted(selected)
            ]
        except AcmPlacementUnavailableError:
            raise
        except Exception as exc:
            raise AcmPlacementUnavailableError(
                f"ACM placement snapshot is unavailable: {exc}"
            ) from exc

        digest_source = {
            "namespace": self.namespace,
            "placement_name": self.placement_name,
            "decision_versions": sorted(decision_versions),
            "clusters": [item.model_dump(mode="json") for item in observations],
        }
        digest = hashlib.sha256(
            json.dumps(
                digest_source, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        return AcmPlacementSnapshot(
            namespace=self.namespace,
            placement_name=self.placement_name,
            snapshot_id=f"sha256:{digest}",
            clusters=observations,
        )

    def _observe_cluster(
        self, cluster_id: str, decision_reasons: list[str]
    ) -> AcmClusterObservation:
        resource = self.api.get_cluster_custom_object(
            group=GROUP,
            version="v1",
            plural="managedclusters",
            name=cluster_id,
        )
        metadata = resource.get("metadata") or {}
        status = resource.get("status") or {}
        conditions = {
            item.get("type"): item
            for item in status.get("conditions") or []
            if item.get("type")
        }
        available = (
            conditions.get("ManagedClusterConditionAvailable", {}).get("status")
            == "True"
        )
        hub_accepted = (
            conditions.get("HubAcceptedManagedCluster", {}).get("status") == "True"
        )
        reasons: list[str] = []
        if not available:
            reasons.append("ManagedClusterConditionAvailable is not True")
        if not hub_accepted:
            reasons.append("HubAcceptedManagedCluster is not True")
        labels = {
            str(key): str(value)
            for key, value in sorted((metadata.get("labels") or {}).items())
        }
        claims = {
            str(item.get("name")): str(item.get("value"))
            for item in status.get("clusterClaims") or []
            if item.get("name")
        }
        return AcmClusterObservation(
            cluster_id=cluster_id,
            resource_version=str(metadata.get("resourceVersion", "")),
            available=available,
            hub_accepted=hub_accepted,
            acm_eligible=available and hub_accepted,
            reasons=reasons,
            decision_reasons=[item for item in decision_reasons if item],
            labels=labels,
            claims=dict(sorted(claims.items())),
        )
