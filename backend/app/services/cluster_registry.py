from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

import yaml

from app.domain.clusters import ClusterTarget


_SOURCE_CONFIG = Path(__file__).resolve().parents[3] / "config" / "clusters.yaml"
DEFAULT_CONFIG = Path("/opt/config/clusters.yaml") if Path("/opt/config/clusters.yaml").exists() else _SOURCE_CONFIG


class ClusterRegistry:
    def __init__(self, targets: Iterable[ClusterTarget] = ()) -> None:
        self._targets = {target.cluster_id: target for target in targets}

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> "ClusterRegistry":
        config_path = Path(path or os.environ.get("CLUSTER_TARGETS_FILE", DEFAULT_CONFIG))
        if not config_path.exists():
            return cls()
        payload = yaml.safe_load(config_path.read_text()) or {}
        return cls(ClusterTarget.model_validate(item) for item in payload.get("clusters", []))

    def get(self, cluster_id: str) -> ClusterTarget:
        target = self._targets.get(cluster_id)
        if target is None:
            raise ValueError(f"Unknown target cluster '{cluster_id}'")
        if not target.enabled:
            raise ValueError(f"Target cluster '{cluster_id}' is disabled")
        return target

    def list_enabled(self) -> list[ClusterTarget]:
        return [target for target in self._targets.values() if target.enabled]

    def eligible(
        self,
        required_capabilities: Iterable[str] = (),
        required_models: Iterable[str] = (),
    ) -> list[ClusterTarget]:
        capabilities = set(required_capabilities)
        models = set(required_models)
        return sorted(
            [
                target
                for target in self.list_enabled()
                if capabilities.issubset(set(target.capabilities))
                and models.issubset(set(target.model_endpoints))
            ],
            key=lambda target: (target.priority, target.cluster_id),
        )

    def select(
        self,
        required_capabilities: Iterable[str] = (),
        required_models: Iterable[str] = (),
        override: Optional[str] = None,
    ) -> ClusterTarget:
        candidates = self.eligible(required_capabilities, required_models)
        if override:
            target = self.get(override)
            if target not in candidates:
                raise ValueError(
                    f"Target cluster '{override}' lacks required capabilities or models"
                )
            return target
        if not candidates:
            raise ValueError("No eligible execution cluster is available")
        return candidates[0]
