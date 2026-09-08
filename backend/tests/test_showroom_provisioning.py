from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem, LabRequest


def _guided_item() -> CatalogItem:
    return CatalogItem(
        catalog_item_id="guided-rag-on-xeon",
        display_name="Guided RAG on Intel Xeon",
        category=CatalogCategory.GUIDED_BUILD,
        status=CatalogStatus.ACTIVE,
        metadata={
            "demo_pages": "try-it",
            "workspace_path": "/try-it",
            "showroom": True,
            "showroom_title": "Build a RAG Assistant",
            "showroom_steps": [
                {"title": "Inspect", "description": "Review the architecture."},
                {"title": "Test", "description": "Send a grounded prompt."},
            ],
        },
    )


def test_guided_catalog_item_adds_showroom_to_plan():
    adapter = object.__new__(OpenShiftProvisioningAdapter)
    adapter._overlay_path = "/tmp/demo"
    request = LabRequest(
        tenant_id="partner-a",
        requester_id="user-a",
        catalog_item_id="guided-rag-on-xeon",
        requested_mode=CatalogCategory.GUIDED_BUILD,
    )

    plan = adapter.create_plan(request, _guided_item())

    assert plan.required_resources["showroom_enabled"] is True
    assert plan.required_resources["showroom_title"] == "Build a RAG Assistant"
    assert len(plan.required_resources["showroom_steps"]) == 2
    assert plan.required_resources["demo_pages"] == "try-it"
    assert plan.required_resources["workspace_path"] == "/try-it"


def test_remote_showroom_plan_carries_target_specific_support_images():
    adapter = object.__new__(OpenShiftProvisioningAdapter)
    adapter._overlay_path = "/tmp/demo"
    adapter._target = SimpleNamespace(
        cluster_id="oberon",
        image_references={
            "showroom_terminal": "quay.io/example/terminal@sha256:" + "a" * 64,
            "showroom_git_cloner": "quay.io/example/cloner@sha256:" + "b" * 64,
        },
    )
    request = LabRequest(
        tenant_id="partner-a",
        requester_id="user-a",
        catalog_item_id="guided-rag-on-xeon",
        requested_mode=CatalogCategory.GUIDED_BUILD,
    )

    plan = adapter.create_plan(request, _guided_item())

    assert plan.required_resources["showroom_support_images"] == adapter._target.image_references


def test_operator_workshop_plan_skips_generic_demo_runtime():
    adapter = object.__new__(OpenShiftProvisioningAdapter)
    adapter._overlay_path = "/tmp/demo"
    item = CatalogItem(
        catalog_item_id="openshift-operators-workshop",
        display_name="OpenShift AI Operator Workshop",
        category=CatalogCategory.GUIDED_BUILD,
        status=CatalogStatus.ACTIVE,
        metadata={
            "showroom": True,
            "showroom_journey": "openshift-operators",
            "operator_workshop": True,
        },
    )
    request = LabRequest(
        tenant_id="partner-a",
        requester_id="user-a",
        catalog_item_id=item.catalog_item_id,
        requested_mode=CatalogCategory.GUIDED_BUILD,
    )

    plan = adapter.create_plan(request, item)

    assert plan.required_resources["operator_workshop"] is True
    assert plan.required_resources["showroom_journey"] == "openshift-operators"


def test_helm_workload_plan_carries_only_declarative_non_secret_contract():
    adapter = object.__new__(OpenShiftProvisioningAdapter)
    adapter._overlay_path = "/tmp/demo"
    item = CatalogItem(
        catalog_item_id="agentops",
        display_name="AgentOps",
        category=CatalogCategory.GUIDED_BUILD,
        status=CatalogStatus.DRAFT,
        provisioner_refs=["helm-workload", "showroom"],
        metadata={
            "showroom": True,
            "workload_gitops_ready": False,
            "workload_repo": "https://github.com/example/workload.git",
            "workload_revision": "a" * 40,
            "workload_deploy_path": "deploy/helm/example",
            "workload_release_name": "example",
            "workload_runtime_secret_name": "example-runtime",
            "workload_runtime_secret_value_path": "runtime.existingSecret",
            "workload_identity_value_path": "identity",
            "workload_helm_values": {"keycloak": {"enabled": False}},
            "workload_ignore_differences": [
                {
                    "group": "",
                    "kind": "ConfigMap",
                    "name": "service-ca",
                    "jsonPointers": ["/data"],
                }
            ],
            "workload_routes": {"ui": "example-ui"},
            "workload_readiness": [
                {
                    "group": "example.io",
                    "version": "v1",
                    "plural": "examples",
                    "name": "example",
                    "condition_type": "Ready",
                    "expected_status": "True",
                    "timeout_seconds": 120,
                }
            ],
            "showroom_tabs": [
                {"id": "terminal", "title": "Terminal", "source": "showroom.terminal"},
                {"id": "app", "title": "App", "source": "workload.route.ui"},
            ],
        },
    )
    request = LabRequest(
        tenant_id="partner-a",
        requester_id="user-a",
        catalog_item_id="agentops",
        requested_mode=CatalogCategory.GUIDED_BUILD,
    )

    plan = adapter.create_plan(request, item)

    assert plan.required_resources["workload_enabled"] is True
    assert plan.required_resources["workload_gitops_ready"] is False
    assert plan.required_resources["workload_revision"] == "a" * 40
    assert plan.required_resources["workload_helm_values"] == {"keycloak": {"enabled": False}}
    assert plan.required_resources["workload_ignore_differences"][0]["name"] == "service-ca"
    assert plan.required_resources["workload_identity_value_path"] == "identity"
    assert plan.required_resources["workload_readiness"][0]["condition_type"] == "Ready"
    assert "maas_api_key" not in plan.required_resources

    with pytest.raises(ValueError, match="not activation-ready"):
        adapter.provision(plan)


def test_resolves_declared_showroom_tabs_from_cluster_and_workload_contract():
    tabs = OpenShiftProvisioningAdapter._resolve_showroom_tabs(
        [
            {"title": "OpenShift", "source": "cluster.console_url"},
            {"title": "Terminal", "source": "showroom.terminal"},
            {"title": "App", "source": "workload.route.ui"},
            {"title": "Grafana", "source": "cluster.grafana_url"},
        ],
        namespace="launchpad-seat-1",
        apps_domain="apps.arena.example.com",
        console_url="https://console.example.com",
        workload_routes={"ui": "mortgage-ai-ui-route"},
        cluster_service_urls={"grafana": "https://grafana.example.com"},
    )

    assert [tab.name for tab in tabs] == ["OpenShift", "Terminal", "App", "Grafana"]
    assert tabs[0].url.endswith("/k8s/ns/launchpad-seat-1/core~v1~Pod")
    assert tabs[1].path == "/terminal"
    assert tabs[2].url == ("https://mortgage-ai-ui-route-launchpad-seat-1.apps.arena.example.com")


def test_unresolved_declared_showroom_tab_fails_closed():
    with pytest.raises(ValueError, match="Cannot resolve Showroom tab"):
        OpenShiftProvisioningAdapter._resolve_showroom_tabs(
            [{"title": "MLflow", "source": "cluster.mlflow_url"}],
            namespace="launchpad-seat-1",
            apps_domain="apps.arena.example.com",
            console_url="https://console.example.com",
            workload_routes={},
            cluster_service_urls={},
        )


def test_runtime_secret_resolver_accepts_only_explicit_dynamic_sources():
    resolved = OpenShiftProvisioningAdapter._resolve_workload_runtime_secret(
        {
            "LLM_API_KEY": "maas_api_key",
            "LLM_BASE_URL": "maas_endpoint",
            "LLM_MODEL": "requested_model",
        },
        {
            "maas_api_key": "sk-seat-secret",
            "maas_endpoint": "https://models.example.com/v1",
            "requested_models": ["granite"],
        },
    )

    assert resolved == {
        "LLM_API_KEY": "sk-seat-secret",
        "LLM_BASE_URL": "https://models.example.com/v1",
        "LLM_MODEL": "granite",
    }

    with pytest.raises(ValueError, match="Unsupported"):
        OpenShiftProvisioningAdapter._resolve_workload_runtime_secret(
            {"PASSWORD": "catalog_literal"}, {"catalog_literal": "unsafe"}
        )


def test_runtime_secret_resolver_generates_and_composes_credentials_without_catalog_secrets():
    resolved = OpenShiftProvisioningAdapter._resolve_workload_runtime_secret(
        {
            "POSTGRES_USER": {"value": "agentops"},
            "POSTGRES_PASSWORD": {"source": "generated_password", "length": 32},
            "DATABASE_URL": {
                "template": (
                    "postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
                    "@mortgage-ai-db:5432/mortgage-ai"
                )
            },
            "S3_ACCESS_KEY": {"source": "generated_password", "length": 24},
            "AUTH_DISABLED": {"value": "true"},
            "LLM_API_KEY": {"source": "maas_api_key"},
            "LLM_MODEL": {"source": "requested_model"},
            "MLFLOW_WORKSPACE": {"source": "namespace"},
        },
        {
            "maas_api_key": "sk-seat-secret",
            "requested_models": ["granite"],
            "namespace": "launchpad-agentops-seat-1",
        },
    )

    assert resolved["POSTGRES_USER"] == "agentops"
    assert len(resolved["POSTGRES_PASSWORD"]) >= 32
    assert resolved["POSTGRES_PASSWORD"] in resolved["DATABASE_URL"]
    assert len(resolved["S3_ACCESS_KEY"]) >= 24
    assert resolved["S3_ACCESS_KEY"] != resolved["POSTGRES_PASSWORD"]
    assert resolved["AUTH_DISABLED"] == "true"
    assert resolved["LLM_API_KEY"] == "sk-seat-secret"
    assert resolved["LLM_MODEL"] == "granite"
    assert resolved["MLFLOW_WORKSPACE"] == "launchpad-agentops-seat-1"


def test_runtime_secret_resolver_uses_a_named_cluster_model_endpoint():
    resolved = OpenShiftProvisioningAdapter._resolve_workload_runtime_secret(
        {
            "EMBEDDING_PROVIDER": {"value": "openai_compatible"},
            "EMBEDDING_MODEL": {"value": "nomic-embed-text-v1.5"},
            "EMBEDDING_BASE_URL": {
                "source": "model_endpoint",
                "model": "nomic-embed-text-v1.5",
            },
        },
        {"model_endpoints": {"nomic-embed-text-v1.5": "http://tei-nomic.fleet-llm-d.svc:8080/v1"}},
    )

    assert resolved["EMBEDDING_BASE_URL"] == ("http://tei-nomic.fleet-llm-d.svc:8080/v1")

    with pytest.raises(ValueError, match="is unavailable"):
        OpenShiftProvisioningAdapter._resolve_workload_runtime_secret(
            {
                "EMBEDDING_BASE_URL": {
                    "source": "model_endpoint",
                    "model": "missing-embedding",
                }
            },
            {"model_endpoints": {}},
        )


def test_runtime_secret_resolver_rejects_literal_sensitive_fields_and_unknown_templates():
    with pytest.raises(ValueError, match="Sensitive runtime field"):
        OpenShiftProvisioningAdapter._resolve_workload_runtime_secret(
            {"LLM_API_KEY": {"value": "embedded-key"}}, {}
        )

    with pytest.raises(ValueError, match="unknown field"):
        OpenShiftProvisioningAdapter._resolve_workload_runtime_secret(
            {"DATABASE_URL": {"template": "postgres://{MISSING}"}}, {}
        )


def test_showroom_runtime_credentials_are_applied_only_as_a_namespaced_secret():
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._apply_workload_runtime_secret = MagicMock()

    adapter._apply_showroom_runtime_secret(
        namespace="launchpad-seat-1",
        resources={
            "workshop_id": "workshop-1",
            "seat_id": "seat-1",
            "session_id": "session-1",
            "tenant_id": "tenant-1",
            "maas_api_key": "sk-seat-secret",
            "maas_endpoint": "https://models.example.com/v1",
            "requested_models": ["granite"],
        },
        cluster_id="arena",
    )

    secret = adapter._apply_workload_runtime_secret.call_args.args[0]
    assert secret["metadata"]["name"] == "launchpad-participant-runtime"
    assert secret["metadata"]["namespace"] == "launchpad-seat-1"
    assert secret["metadata"]["labels"]["launchpad.redhat.com/session-id"] == "session-1"
    assert secret["stringData"] == {
        "MAAS_API_KEY": "sk-seat-secret",
        "MAAS_ENDPOINT": "https://models.example.com",
        "MAAS_API_URL": "https://models.example.com/v1",
        "MAAS_MODEL": "granite",
    }


def test_https_model_seat_receives_the_control_plane_ca_bundle():
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._control_core_v1 = MagicMock()
    adapter._core_v1 = MagicMock()
    adapter._control_core_v1.read_namespaced_config_map.return_value = SimpleNamespace(
        data={"ca-bundle.crt": "-----BEGIN CERTIFICATE-----\ntrusted\n-----END CERTIFICATE-----\n"}
    )

    adapter._apply_model_ca_bundle(
        "launchpad-seat-1",
        resources={
            "workshop_id": "workshop-1",
            "seat_id": "seat-1",
            "session_id": "session-1",
            "tenant_id": "tenant-1",
        },
        cluster_id="brutus",
    )

    adapter._control_core_v1.read_namespaced_config_map.assert_called_once_with(
        "launchpad-cluster-ca-bundle", "partner-ai-launchpad"
    )
    body = adapter._core_v1.create_namespaced_config_map.call_args.kwargs["body"]
    assert body.metadata.name == "launchpad-model-ca-bundle"
    assert body.metadata.namespace == "launchpad-seat-1"
    assert body.metadata.labels["launchpad.redhat.com/cluster-id"] == "brutus"
    assert "BEGIN CERTIFICATE" in body.data["ca-bundle.crt"]


def test_guided_workspace_deep_links_to_the_rag_experience():
    url = OpenShiftProvisioningAdapter._workspace_url("https://workspace.example.test", "/try-it")

    assert url == "https://workspace.example.test/try-it"


def test_content_workspace_route_uses_stable_openshift_route_hostname():
    url = OpenShiftProvisioningAdapter._content_workspace_url(
        "solution-ui", "launchpad-seat-agent-1", "apps.arena.example"
    )

    assert url == ("https://solution-ui-launchpad-seat-agent-1.apps.arena.example")


def test_showroom_is_deployed_by_gitops_not_inline_html():
    assert not hasattr(OpenShiftProvisioningAdapter, "_showroom_html")
    assert not hasattr(OpenShiftProvisioningAdapter, "_deploy_showroom")


def test_showroom_prefers_model_endpoint_carried_by_provisioning_plan(monkeypatch):
    monkeypatch.setenv("LITELLM_API_BASE", "http://global-litellm:4000/v1")

    endpoint = OpenShiftProvisioningAdapter._showroom_maas_endpoint(
        {
            "maas_endpoint": "http://arena-tools:8000/v1",
        }
    )

    assert endpoint == "http://arena-tools:8000"


def test_wait_for_showroom_route_accepts_chart_proxy_route(monkeypatch):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    route_snapshots = iter(
        [
            {"demo": "https://demo.example.test"},
            {
                "demo": "https://demo.example.test",
                "showroom-proxy": "https://showroom.example.test",
            },
        ]
    )
    adapter._get_routes = lambda _namespace: next(route_snapshots)
    monkeypatch.setattr("app.adapters.openshift.provisioning.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "app.adapters.openshift.provisioning.requests.get",
        lambda *_args, **_kwargs: MagicMock(status_code=200),
    )

    routes = adapter._wait_for_showroom_route("lab-namespace")

    assert routes["showroom-proxy"] == "https://showroom.example.test"


def test_wait_for_showroom_route_uses_configured_ca_bundle(monkeypatch):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._get_routes = lambda _namespace: {
        "showroom": "https://showroom.example.test"
    }
    request = MagicMock(return_value=MagicMock(status_code=200))
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/etc/launchpad-ca/ca-bundle.crt")
    monkeypatch.setattr("app.adapters.openshift.provisioning.requests.get", request)

    adapter._wait_for_showroom_route("lab-namespace")

    request.assert_called_once_with(
        "https://showroom.example.test",
        timeout=5,
        verify="/etc/launchpad-ca/ca-bundle.crt",
        allow_redirects=True,
    )


def test_wait_for_showroom_route_requires_http_200(monkeypatch):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._get_routes = lambda _namespace: {"showroom": "https://showroom.example.test"}
    responses = iter([MagicMock(status_code=503), MagicMock(status_code=200)])
    request = MagicMock(side_effect=lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr("app.adapters.openshift.provisioning.requests.get", request)
    monkeypatch.setattr("app.adapters.openshift.provisioning.time.sleep", lambda _seconds: None)

    routes = adapter._wait_for_showroom_route("lab-namespace")

    assert routes["showroom"] == "https://showroom.example.test"
    assert request.call_count == 2


def test_showroom_namespace_is_labeled_for_namespaced_argocd(monkeypatch):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._core_v1 = MagicMock()
    monkeypatch.setenv("LAUNCHPAD_CONTROL_PLANE_ID", "arena-primary")

    adapter._create_namespace("lab-showroom", {"argocd.argoproj.io/managed-by": "argocd"})

    body = adapter._core_v1.create_namespace.call_args.kwargs["body"]
    assert body.metadata.labels["argocd.argoproj.io/managed-by"] == "argocd"
    assert body.metadata.labels["launchpad.redhat.com/control-plane-id"] == "arena-primary"


def test_workshop_participant_gets_edit_only_in_seat_namespace():
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._rbac_v1 = MagicMock()

    adapter._grant_participant_access("seat-namespace", "workshop-user-1")

    call = adapter._rbac_v1.create_namespaced_role_binding.call_args
    assert call.kwargs["namespace"] == "seat-namespace"
    binding = call.kwargs["body"]
    assert binding.role_ref.name == "edit"
    assert binding.subjects[0].kind == "User"
    assert binding.subjects[0].name == "workshop-user-1"


def test_flightpath_control_plane_is_bound_only_inside_the_seat_namespace(
    monkeypatch,
):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._rbac_v1 = MagicMock()
    monkeypatch.setenv(
        "REMOTE_CONTROL_PLANE_SERVICE_ACCOUNT_NAMESPACE", "partner-ai-launchpad"
    )
    monkeypatch.setenv(
        "REMOTE_PROVISIONER_SERVICE_ACCOUNT", "launchpad-provisioner-flightpath"
    )
    monkeypatch.setenv(
        "REMOTE_ARGOCD_SERVICE_ACCOUNT", "launchpad-argocd-manager-flightpath"
    )

    adapter._grant_remote_control_plane_access("launchpad-workshop-seat-01")

    calls = adapter._rbac_v1.create_namespaced_role_binding.call_args_list
    assert len(calls) == 2
    assert {call.kwargs["namespace"] for call in calls} == {
        "launchpad-workshop-seat-01"
    }
    bindings = [call.kwargs["body"] for call in calls]
    assert {binding.role_ref.name for binding in bindings} == {
        "launchpad-flightpath-seat-manager",
        "launchpad-flightpath-argocd-seat-manager",
    }
    assert {binding.subjects[0].name for binding in bindings} == {
        "launchpad-provisioner-flightpath",
        "launchpad-argocd-manager-flightpath",
    }


def test_agentops_workshop_participant_gets_namespaced_application_log_view():
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._rbac_v1 = MagicMock()

    adapter._grant_participant_access(
        "seat-namespace", "workshop-user-1", grant_application_logs=True
    )

    calls = adapter._rbac_v1.create_namespaced_role_binding.call_args_list
    assert len(calls) == 2
    assert {call.kwargs["body"].role_ref.name for call in calls} == {
        "edit",
        "cluster-logging-application-view",
    }
    assert {call.kwargs["namespace"] for call in calls} == {"seat-namespace"}


def test_guided_lab_namespace_keeps_generated_showroom_host_label_valid():
    namespace = OpenShiftProvisioningAdapter._demo_namespace(
        "smoke-test-tenant",
        "guided-rag-on-xeon",
        "af85a6",
    )

    assert namespace == "launchpad-smoke-test-tenant-guided-rag-on-xeon-af85a6"
    assert len(f"showroom-{namespace}") <= 63


def test_guided_seat_namespace_can_use_stable_seat_suffix():
    seat_id = "003606bd-5b75-40dc-8eb8-8b7533c5de04"
    suffix = seat_id.replace("-", "")[:6]

    namespace = OpenShiftProvisioningAdapter._demo_namespace(
        "smoke-test-tenant", "guided-rag-on-xeon", suffix
    )

    assert namespace.endswith("-003606")


def test_create_plan_persists_exact_namespace_used_for_the_workshop_seat():
    adapter = object.__new__(OpenShiftProvisioningAdapter)
    adapter._overlay_path = "/tmp/demo"
    item = _guided_item()
    request = LabRequest(
        tenant_id="smoke-test-tenant",
        requester_id="participant-1",
        catalog_item_id=item.catalog_item_id,
        requested_mode=CatalogCategory.GUIDED_BUILD,
        metadata={"seat_id": "003606bd-5b75-40dc-8eb8-8b7533c5de04"},
    )

    plan = adapter.create_plan(request, item)

    assert plan.target_namespace == ("launchpad-smoke-test-tenant-guided-rag-on-xeon-003606")
    assert plan.required_resources["tenant_id"] == "smoke-test-tenant"


def test_catalog_namespace_slug_leaves_room_for_operator_generated_routes():
    adapter = object.__new__(OpenShiftProvisioningAdapter)
    adapter._overlay_path = "/tmp/demo"
    base_item = _guided_item()
    item = base_item.model_copy(
        update={
            "catalog_item_id": "agentops-observability",
            "metadata": {**base_item.metadata, "namespace_slug": "agentops"},
        }
    )
    request = LabRequest(
        tenant_id="smoke-test-tenant",
        requester_id="participant-1",
        catalog_item_id=item.catalog_item_id,
        requested_mode=CatalogCategory.GUIDED_BUILD,
        metadata={"seat_id": "8b8f64ab-3bbf-432f-946c-3d375e21a483"},
    )

    plan = adapter.create_plan(request, item)

    assert "-agentops-" in plan.target_namespace
    assert len(f"ds-pipeline-dspa-{plan.target_namespace}") <= 63


def test_wait_for_workload_readiness_retries_until_declared_condition_is_true(
    monkeypatch,
):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._custom_objects = MagicMock()
    adapter._custom_objects.get_namespaced_custom_object.side_effect = [
        {"status": {"conditions": [{"type": "Ready", "status": "False"}]}},
        {"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
    ]
    monkeypatch.setattr("app.adapters.openshift.provisioning.time.sleep", lambda _seconds: None)

    adapter._wait_for_workload_readiness(
        "launchpad-agentops-seat-1",
        [
            {
                "group": "datasciencepipelinesapplications.opendatahub.io",
                "version": "v1",
                "plural": "datasciencepipelinesapplications",
                "name": "dspa",
                "condition_type": "Ready",
                "expected_status": "True",
                "timeout_seconds": 60,
            }
        ],
    )

    assert adapter._custom_objects.get_namespaced_custom_object.call_count == 2


def test_wait_for_workload_readiness_fails_closed_when_condition_never_matches(
    monkeypatch,
):
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._custom_objects = MagicMock()
    adapter._custom_objects.get_namespaced_custom_object.return_value = {
        "status": {"conditions": [{"type": "Ready", "status": "False"}]}
    }
    monkeypatch.setattr("app.adapters.openshift.provisioning.time.sleep", lambda _seconds: None)

    with pytest.raises(ValueError, match="dspa.*Ready=True"):
        adapter._wait_for_workload_readiness(
            "launchpad-agentops-seat-1",
            [
                {
                    "group": "datasciencepipelinesapplications.opendatahub.io",
                    "version": "v1",
                    "plural": "datasciencepipelinesapplications",
                    "name": "dspa",
                    "condition_type": "Ready",
                    "expected_status": "True",
                    "timeout_seconds": 0,
                }
            ],
        )


def test_gateway_pvc_uses_configured_storage_class():
    manifest = """apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
spec:
  accessModes: [ReadWriteOnce]
"""

    rendered = OpenShiftProvisioningAdapter._inject_storage_class(manifest, "nfs-storage")

    assert "storageClassName: nfs-storage" in rendered
