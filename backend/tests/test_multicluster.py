from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.adapters.openshift.client_factory import ClusterClientFactory
from app.adapters.openshift.showroom_gitops import ShowroomSeat, build_showroom_application
from app.domain.clusters import ClusterTarget
from app.domain.models import LabRequest, Workshop
from app.services.cluster_registry import ClusterRegistry
from app.services.provisioning import ProvisioningService


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


def test_registry_can_inspect_disabled_target_without_making_it_placeable():
    disabled = target("brutus", 20, ["cpu", "openshift"]).model_copy(
        update={"enabled": False}
    )
    registry = ClusterRegistry([disabled])

    assert registry.inspect("brutus") == disabled
    assert registry.list_all() == [disabled]
    with pytest.raises(ValueError, match="disabled"):
        registry.get("brutus")


def test_disabled_target_requires_explicit_certification_override():
    disabled = target(
        "oberon",
        50,
        ["cpu", "openshift", "showroom", "model_endpoint"],
        {"granite-2b-cpu": "https://model"},
    ).model_copy(update={"enabled": False})
    registry = ClusterRegistry([disabled])

    with pytest.raises(ValueError, match="disabled"):
        registry.select(
            ["openshift", "showroom", "model_endpoint"],
            ["granite-2b-cpu"],
            override="oberon",
        )

    selected = registry.select(
        ["openshift", "showroom", "model_endpoint"],
        ["granite-2b-cpu"],
        override="oberon",
        allow_disabled_override=True,
    )

    assert selected == disabled


def test_workshop_certification_preview_can_target_disabled_cluster_only_explicitly():
    disabled = target(
        "oberon",
        50,
        ["openshift", "showroom", "model_endpoint"],
        {"granite-2b-cpu": "https://model"},
    ).model_copy(update={"enabled": False})
    catalog = MagicMock()
    catalog.get_item.return_value = SimpleNamespace(
        required_capabilities=["openshift", "showroom", "model_endpoint"],
        metadata={"required_models": ["granite-2b-cpu"], "max_workshop_seats": 25},
    )
    service = ProvisioningService(
        catalog=catalog,
        cluster_registry=ClusterRegistry([disabled]),
    )
    service.check_workshop_capacity = MagicMock(return_value=(True, "capacity available"))

    ordinary = service.preview_workshop_capacity(
        Workshop(
            tenant_id="pilot-tenant",
            catalog_item_id="intel-llm-cpu-serving",
            num_users=1,
            target_cluster="oberon",
        )
    )
    certification = service.preview_workshop_capacity(
        Workshop(
            tenant_id="pilot-tenant",
            catalog_item_id="intel-llm-cpu-serving",
            num_users=1,
            target_cluster="oberon",
            certification_override=True,
        )
    )

    assert ordinary["can_provision"] is False
    assert ordinary["reason"] == "Target cluster 'oberon' is disabled"
    assert certification["can_provision"] is True
    assert certification["selected_cluster"] == "oberon"


def test_persisted_target_lifecycle_can_reach_disabled_cluster_for_cleanup():
    factory = MagicMock()
    expected = MagicMock()
    factory.clients.return_value = expected
    service = ProvisioningService.__new__(ProvisioningService)
    service.cluster_client_factory = factory

    assert service._target_clients("brutus") is expected
    factory.clients.assert_called_once_with("brutus", allow_disabled=True)


def test_client_factory_inspection_does_not_bypass_disabled_placement():
    disabled = target("brutus", 20, ["cpu", "openshift"]).model_copy(
        update={"enabled": False}
    )
    registry = ClusterRegistry([disabled])
    factory = ClusterClientFactory(registry)

    with patch.object(factory, "_remote_client", return_value=MagicMock()):
        inspected = factory.clients("brutus", allow_disabled=True)

    assert inspected.core is not None
    with pytest.raises(ValueError, match="disabled"):
        factory.clients("brutus")


def test_fleet_inspection_reports_healthy_disabled_target_as_ineligible():
    disabled = target("brutus", 20, ["cpu", "openshift"]).model_copy(
        update={"enabled": False}
    )
    registry = ClusterRegistry([disabled])
    ready = SimpleNamespace(type="Ready", status="True", last_transition_time=None)
    node = SimpleNamespace(
        metadata=SimpleNamespace(name="worker-0", labels={}),
        spec=SimpleNamespace(unschedulable=False),
        status=SimpleNamespace(
            conditions=[ready],
            allocatable={"cpu": "64", "memory": "128Gi", "pods": "250"},
        ),
    )
    core = MagicMock()
    core.list_node.return_value.items = [node]
    core.list_pod_for_all_namespaces.return_value.items = []
    factory = MagicMock()
    factory.clients.return_value = SimpleNamespace(core=core)
    service = ProvisioningService(
        cluster_registry=registry,
        cluster_client_factory=factory,
    )

    result = service.get_cluster_fleet_health(include_disabled=True)

    assert result[0]["cluster_id"] == "brutus"
    assert result[0]["healthy"] is True
    assert result[0]["eligible"] is False
    assert result[0]["configured_enabled"] is False
    assert result[0]["inspection_only"] is True
    assert result[0]["available_pods"] == 250
    factory.clients.assert_called_once_with("brutus", allow_disabled=True)


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


def test_repository_cluster_config_registers_remote_targets_fail_closed():
    path = Path(__file__).resolve().parents[2] / "config" / "clusters.yaml"
    document = __import__("yaml").safe_load(path.read_text())
    registry = ClusterRegistry.from_file(str(path))

    targets = {item["cluster_id"]: item for item in document["clusters"]}
    assert set(targets) == {"arena", "oberon", "brutus"}
    assert {c.cluster_id for c in registry.list_enabled()} == {"arena"}
    assert targets["oberon"] == {
        "cluster_id": "oberon",
        "display_name": "Oberon Primary",
        "api_url": "https://api.oberon.fm2aihpcsed.com:6443",
        "ingress_domain": "apps.oberon.fm2aihpcsed.com",
        "console_url": "https://console-openshift-console.apps.oberon.fm2aihpcsed.com",
        "storage_class": "launchpad-nfs-ephemeral",
        "credential_secret": "partner-ai-launchpad/launchpad-oberon-kubeconfig",
        "local": False,
        "priority": 50,
        "enabled": False,
        "public_access_enabled": False,
        "public_ingress_domain": "",
        "public_console_url": "",
        "public_oauth_url": "",
        "capabilities": [
            "cpu", "gaudi", "gaudi_direct", "openshift", "operators",
            "openshift-ai", "showroom", "model_endpoint", "vector_db",
            "kafka", "workbench",
        ],
        "model_endpoints": targets["oberon"]["model_endpoints"],
    }
    assert targets["brutus"] == {
        "cluster_id": "brutus",
        "display_name": "Brutus CPU Execution",
        "api_url": "https://api.brutus.fm2aihpcsed.com:6443",
        "ingress_domain": "apps.brutus.fm2aihpcsed.com",
        "console_url": "https://console-openshift-console.apps.brutus.fm2aihpcsed.com",
        "storage_class": "launchpad-nfs-ephemeral",
        "credential_secret": "partner-ai-launchpad/launchpad-brutus-kubeconfig",
        "local": False,
        "priority": 20,
        "enabled": False,
        "public_access_enabled": False,
        "public_ingress_domain": "",
        "public_console_url": "",
        "public_oauth_url": "",
        "capabilities": [
            "cpu", "openshift", "operators", "showroom", "model_endpoint",
        ],
        "model_endpoints": {
            "granite-3.2-8b-tools": (
                "https://vllm-granite-3-2-8b-tools-fleet-llm-d."
                "apps.arena.fm2aihpcsed.com/v1"
            )
        },
    }


def test_arena_overlay_carries_disabled_remote_targets():
    root = Path(__file__).resolve().parents[2]
    document = __import__("yaml").safe_load(
        (root / "deploy/launchpad/overlays/arena/arena-clusters.yaml").read_text()
    )
    config = __import__("yaml").safe_load(document["data"]["clusters.yaml"])
    targets = {item["cluster_id"]: item for item in config["clusters"]}

    assert set(targets) == {"arena", "oberon", "brutus"}
    assert targets["arena"].get("enabled", True) is True
    assert targets["arena"]["local"] is True
    for cluster_id in ("oberon", "brutus"):
        assert targets[cluster_id]["enabled"] is False
        assert targets[cluster_id]["local"] is False
        assert targets[cluster_id]["credential_secret"].startswith(
            "partner-ai-launchpad/launchpad-"
        )


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

    assert selected.cluster_id == "arena"
    assert set(catalog_item["metadata"]["required_models"]).issubset(
        selected.model_endpoints
    )
    assert set(registry.get("arena").model_endpoints) == {
        "granite-2b-cpu",
        "granite-3.2-8b-tools",
        "nomic-embed-text-v1.5",
    }


def test_arena_public_cert_registry_retains_model_routing():
    root = Path(__file__).resolve().parents[2]
    registry = ClusterRegistry.from_file(
        str(root / "config" / "clusters-arena-cert.yaml")
    )

    selected = registry.select(
        required_capabilities=["openshift", "showroom", "model_endpoint"],
        required_models=["granite-2b-cpu"],
        override="arena",
        require_public_access=True,
    )

    assert selected.cluster_id == "arena"
    assert "control-plane" in selected.capabilities


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


def test_preflight_receives_selected_cluster_model_endpoints():
    service = ProvisioningService.__new__(ProvisioningService)
    service.cluster_registry = ClusterRegistry([
        target(
            "arena",
            10,
            ["openshift", "model_endpoint"],
            {"granite-3.2-8b-tools": "http://arena-tools:8000/v1"},
        ),
    ])
    service.preflight = MagicMock()
    catalog_item = SimpleNamespace(metadata={"required_models": ["granite-3.2-8b-tools"]})

    service._run_preflight(catalog_item, "arena")

    service.preflight.check.assert_called_once_with(
        catalog_item,
        model_endpoints={
            "granite-3.2-8b-tools": "http://arena-tools:8000/v1",
        },
    )


def test_showroom_model_endpoint_comes_from_selected_cluster_registry():
    service = ProvisioningService.__new__(ProvisioningService)
    service.cluster_registry = ClusterRegistry([
        target(
            "arena",
            10,
            ["openshift", "model_endpoint"],
            {"granite-3.2-8b-tools": "http://arena-tools:8000/v1"},
        ),
    ])

    endpoint = service._selected_model_endpoint(
        "arena", ["granite-3.2-8b-tools"]
    )

    assert endpoint == "http://arena-tools:8000/v1"


def test_arena_only_registry_uses_arena_as_control_cluster(monkeypatch):
    monkeypatch.delenv("LAUNCHPAD_CONTROL_CLUSTER_REF", raising=False)
    service = ProvisioningService.__new__(ProvisioningService)
    service.cluster_registry = ClusterRegistry([
        target("arena", 10, ["cpu", "openshift", "control-plane"]),
    ])

    assert service._control_cluster_ref("arena") == "arena"


def test_explicit_control_cluster_overrides_registry(monkeypatch):
    monkeypatch.setenv("LAUNCHPAD_CONTROL_CLUSTER_REF", "arena")
    service = ProvisioningService.__new__(ProvisioningService)
    service.cluster_registry = ClusterRegistry([
        target("oberon", 50, ["openshift", "control-plane"]),
        target("arena", 10, ["openshift"]),
    ])

    assert service._control_cluster_ref("oberon") == "arena"


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


def test_remote_provisioner_can_bind_only_declared_participant_roles():
    path = Path(__file__).resolve().parents[2] / "deploy" / "multicluster" / "arena-rbac.yaml"
    documents = list(__import__("yaml").safe_load_all(path.read_text()))
    role = next(
        doc
        for doc in documents
        if doc.get("kind") == "ClusterRole"
        and doc["metadata"]["name"] == "launchpad-remote-provisioner"
    )
    bind_rules = [rule for rule in role["rules"] if "bind" in rule.get("verbs", [])]

    assert bind_rules == [{
        "apiGroups": ["rbac.authorization.k8s.io"],
        "resources": ["clusterroles"],
        "resourceNames": [
            "edit",
            "system:image-puller",
            "cluster-logging-application-view",
        ],
        "verbs": ["bind"],
    }]
