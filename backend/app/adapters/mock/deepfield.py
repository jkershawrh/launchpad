from __future__ import annotations

from typing import Dict, List

from app.domain.orchestration import DeepFieldSignal


class MockDeepFieldAdapter:

    def __init__(self, signals: Dict[str, List[DeepFieldSignal]] | None = None):
        self._signals = signals or {
            "mock-cluster-1": [
                DeepFieldSignal(
                    cluster_name="mock-cluster-1",
                    metric_type="cpu_utilization",
                    value=0.45,
                    threshold=0.80,
                    status="normal",
                ),
                DeepFieldSignal(
                    cluster_name="mock-cluster-1",
                    metric_type="gpu_utilization",
                    value=0.30,
                    threshold=0.90,
                    status="normal",
                ),
            ],
        }

    def get_cluster_signals(self, cluster_name: str) -> List[DeepFieldSignal]:
        return self._signals.get(cluster_name, [])

    def get_fleet_overview(self) -> Dict[str, List[DeepFieldSignal]]:
        return dict(self._signals)


class MockUnhealthyDeepFieldAdapter:

    def __init__(self, unhealthy_cluster: str = "cluster-a"):
        self._unhealthy = unhealthy_cluster

    def get_cluster_signals(self, cluster_name: str) -> List[DeepFieldSignal]:
        if cluster_name == self._unhealthy:
            return [
                DeepFieldSignal(
                    cluster_name=cluster_name,
                    metric_type="cpu_utilization",
                    value=0.95,
                    threshold=0.80,
                    status="critical",
                ),
                DeepFieldSignal(
                    cluster_name=cluster_name,
                    metric_type="error_rate",
                    value=0.15,
                    threshold=0.05,
                    status="critical",
                ),
            ]
        return [
            DeepFieldSignal(
                cluster_name=cluster_name,
                metric_type="cpu_utilization",
                value=0.40,
                threshold=0.80,
                status="normal",
            ),
        ]

    def get_fleet_overview(self) -> Dict[str, List[DeepFieldSignal]]:
        return {
            self._unhealthy: self.get_cluster_signals(self._unhealthy),
            "healthy-cluster": self.get_cluster_signals("healthy-cluster"),
        }


class MockDeepFieldDown:

    def get_cluster_signals(self, cluster_name: str) -> List[DeepFieldSignal]:
        return []

    def get_fleet_overview(self) -> Dict[str, List[DeepFieldSignal]]:
        return {}
