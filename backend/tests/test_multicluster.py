from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.clusters import ClusterTarget
from app.services.cluster_registry import ClusterRegistry
from app.services.provisioning import ProvisioningService
from app.domain.models import LabRequest
from app.adapters.openshift.showroom_gitops import ShowroomSeat, build_showroom_application


def target(cluster_id, priority, capabilities, models=None):
    return ClusterTarget(
        cluster_id=cluster_id,
        display_name=cluster_id.title(),
        ingress_domain=f"apps.{cluster_id}.example.com",
        priority=priority,
        capabilities=capabilities,
        model_endpoints=models or {},
        local=cluster_id == "oberon",
        credential_secret=None if cluster_id == "oberon" else "launchpad/remote",
    )


def test_registry_prefers_arena_for_cpu_operator_workloads():
    registry = ClusterRegistry([
        target("oberon", 50, ["cpu", "openshift", "operators", "gaudi"]),
        target("arena", 10, ["cpu", "openshift", "operators"]),
    ])
    assert registry.select(["openshift", "operators"]).cluster_id == "arena"


def test_registry_filters_capabilities_and_models_and_validates_override():
    registry = ClusterRegistry([
        target("oberon", 50, ["openshift", "gaudi"], {"large": "https://model"}),
        target("arena", 10, ["openshift"], {"small": "https://model"}),
    ])
    assert registry.select(["openshift", "gaudi"], ["large"]).cluster_id == "oberon"
    with pytest.raises(ValueError, match="lacks required"):
        registry.select(["gaudi"], override="arena")


def test_showroom_application_targets_selected_remote_cluster():
    app = build_showroom_application(ShowroomSeat(
        namespace="launchpad-seat-1",
        workshop_id="workshop-1",
        seat_id="seat-1",
        participant_id="user-1",
        workspace_url="",
        content_repo_url="https://github.com/example/lab.git",
        content_ref="main",
        apps_domain="apps.arena.example.com",
        destination_server="https://api.arena.example.com:6443",
        storage_class="nfs-storage",
        cluster_id="arena",
    ))
    assert app["spec"]["destination"] == {
        "server": "https://api.arena.example.com:6443",
        "namespace": "launchpad-seat-1",
    }
    assert app["metadata"]["labels"]["launchpad.redhat.com/cluster-id"] == "arena"
    assert "storageClass: nfs-storage" in app["spec"]["source"]["helm"]["values"]


def test_repository_cluster_config_has_oberon_and_arena():
    path = Path(__file__).resolve().parents[2] / "config" / "clusters.yaml"
    registry = ClusterRegistry.from_file(str(path))
    assert {c.cluster_id for c in registry.list_enabled()} == {"oberon", "arena"}


def test_active_ai_sandbox_has_an_eligible_cluster():
    root = Path(__file__).resolve().parents[2]
    registry = ClusterRegistry.from_file(str(root / "config" / "clusters.yaml"))
    catalog_item = __import__("yaml").safe_load(
        (root / "catalog" / "ai-sandbox" / "catalog-item.yaml").read_text()
    )

    selected = registry.select(
        required_capabilities=catalog_item["required_capabilities"],
        required_models=catalog_item["metadata"]["required_models"],
    )

    assert selected.cluster_id == "oberon"
    assert set(catalog_item["metadata"]["required_models"]).issubset(
        selected.model_endpoints
    )


def test_sandbox_model_selection_controls_cluster_placement():
    service = ProvisioningService.__new__(ProvisioningService)
    service.cluster_registry = ClusterRegistry([
        target("oberon", 50, ["openshift", "model_endpoint"], {"model-a": "https://a"}),
        target("arena", 10, ["openshift", "model_endpoint"], {"model-b": "https://b"}),
    ])
    request = LabRequest(
        tenant_id="tenant",
        requester_id="user",
        catalog_item_id="ai-sandbox",
        requested_mode="open_sandbox",
        requested_models=["model-a"],
    )
    catalog_item = SimpleNamespace(
        required_capabilities=["openshift", "model_endpoint"],
        default_hardware_profile="xeon-basic",
        metadata={"required_models": ["model-b"]},
    )

    assert service._select_target_cluster(request, catalog_item) == "oberon"


def test_remote_argocd_role_can_bind_only_edit():
    path = Path(__file__).resolve().parents[2] / "deploy" / "multicluster" / "arena-argocd-rbac.yaml"
    documents = list(__import__("yaml").safe_load_all(path.read_text()))
    role = next(doc for doc in documents if doc.get("kind") == "ClusterRole")
    bind_rules = [rule for rule in role["rules"] if "bind" in rule.get("verbs", [])]
    assert bind_rules == [{
        "apiGroups": ["rbac.authorization.k8s.io"],
        "resources": ["clusterroles"],
        "resourceNames": ["edit"],
        "verbs": ["bind"],
    }]
