from pathlib import Path
from types import SimpleNamespace

import yaml


class _Custom:
    def list_cluster_custom_object(self, **_kwargs):
        return {
            "items": [{
                "metadata": {"namespace": "seat-one", "name": "workload-a"},
                "containers": [
                    {"usage": {"cpu": "250m", "memory": "512Mi"}},
                    {"usage": {"cpu": "125000000n", "memory": "1Gi"}},
                ],
            }]
        }


class _Core:
    def list_pod_for_all_namespaces(self):
        status = SimpleNamespace(
            container_statuses=[
                SimpleNamespace(ready=True, restart_count=1),
                SimpleNamespace(ready=True, restart_count=0),
            ],
        )
        return SimpleNamespace(items=[SimpleNamespace(
            metadata=SimpleNamespace(namespace="seat-one", name="workload-a"),
            status=status,
        )])


class _Factory:
    def clients(self, cluster_ref, allow_disabled=True):
        assert cluster_ref == "arena"
        assert allow_disabled is True
        return SimpleNamespace(custom=_Custom(), core=_Core())


def test_collects_current_usage_and_restarts_by_session_namespace():
    from app.services.seat_resource_metrics import collect_seat_resource_metrics

    session = SimpleNamespace(session_id="session-1", namespace="seat-one", cluster_ref="arena")
    result = collect_seat_resource_metrics([session], _Factory())

    assert result["session-1"]["available"] is True
    assert result["session-1"]["cpu_millicores"] == 375
    assert result["session-1"]["memory_mib"] == 1536
    assert result["session-1"]["pod_count"] == 1
    assert result["session-1"]["ready_pods"] == 1
    assert result["session-1"]["restarts"] == 1
    assert result["session-1"]["terminal_reconnects"] is None


def test_cluster_metrics_failure_degrades_to_unavailable_signal():
    from app.services.seat_resource_metrics import collect_seat_resource_metrics

    class BrokenFactory:
        def clients(self, *_args, **_kwargs):
            raise RuntimeError("metrics unavailable")

    session = SimpleNamespace(session_id="session-1", namespace="seat-one", cluster_ref="arena")
    result = collect_seat_resource_metrics([session], BrokenFactory())

    assert result["session-1"]["available"] is False
    assert result["session-1"]["reason"] == "cluster metrics unavailable"


def test_local_and_remote_provisioners_can_read_pod_metrics():
    root = Path(__file__).parents[2]
    for relative in ("deploy/launchpad/base/rbac.yaml", "deploy/multicluster/arena-rbac.yaml"):
        documents = list(yaml.safe_load_all((root / relative).read_text()))
        role = next(item for item in documents if item and item.get("kind") == "ClusterRole")
        assert any(
            rule.get("apiGroups") == ["metrics.k8s.io"]
            and rule.get("resources") == ["pods"]
            and {"get", "list"} <= set(rule.get("verbs", []))
            for rule in role["rules"]
        )
