from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml
from app.adapters.openshift.workload_gitops import (
    WorkloadGitOpsAdapter,
    WorkloadSeat,
    build_runtime_secret,
    build_workload_application,
    workload_application_name,
)
from kubernetes.client.exceptions import ApiException


def _seat(**updates) -> WorkloadSeat:
    values = {
        "namespace": "launchpad-seat-1",
        "workshop_id": "workshop-1",
        "seat_id": "seat-1",
        "session_id": "session-1",
        "tenant_id": "tenant-1",
        "cluster_id": "arena",
        "destination_server": "https://api.arena.example.com:6443",
        "repo_url": "https://github.com/example/workload.git",
        "revision": "a" * 40,
        "deploy_path": "deploy/helm/example",
        "release_name": "example",
        "helm_values": {"keycloak": {"enabled": False}},
        "runtime_secret_name": "example-runtime",
        "runtime_secret_value_path": "runtime.existingSecret",
        "identity_value_path": "identity",
    }
    values.update(updates)
    return WorkloadSeat(**values)


def test_builds_git_pinned_cluster_aware_workload_application():
    app = build_workload_application(_seat())

    assert app["metadata"]["name"] == workload_application_name("launchpad-seat-1")
    assert app["metadata"]["labels"] == {
        "app.kubernetes.io/component": "workload",
        "app.kubernetes.io/managed-by": "launchpad",
        "launchpad.redhat.com/workshop-id": "workshop-1",
        "launchpad.redhat.com/seat-id": "seat-1",
        "launchpad.redhat.com/session-id": "session-1",
        "launchpad.redhat.com/tenant": "tenant-1",
        "launchpad.redhat.com/cluster-id": "arena",
    }
    assert app["spec"]["source"]["repoURL"] == ("https://github.com/example/workload.git")
    assert app["spec"]["source"]["targetRevision"] == "a" * 40
    assert app["spec"]["source"]["path"] == "deploy/helm/example"
    assert app["spec"]["destination"] == {
        "server": "https://api.arena.example.com:6443",
        "namespace": "launchpad-seat-1",
    }
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    assert values == {
        "keycloak": {"enabled": False},
        "runtime": {"existingSecret": "example-runtime"},
        "identity": {
            "workshopId": "workshop-1",
            "seatId": "seat-1",
            "sessionId": "session-1",
            "tenantId": "tenant-1",
            "clusterId": "arena",
        },
    }


def test_references_precreated_runtime_secret_without_argocd_owning_its_data():
    app = build_workload_application(_seat())
    rendered = yaml.safe_dump(app)

    assert "sk-seat-secret" not in rendered
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    assert values["runtime"]["existingSecret"] == "example-runtime"
    assert "ignoreDifferences" not in app["spec"]


def test_supports_narrow_catalog_declared_ignore_differences():
    rule = {
        "group": "",
        "kind": "ConfigMap",
        "name": "agentops-pipeline-service-ca",
        "jsonPointers": ["/data"],
    }

    app = build_workload_application(_seat(ignore_differences=(rule,)))

    assert app["spec"]["ignoreDifferences"] == [rule]
    assert "RespectIgnoreDifferences=true" in app["spec"]["syncPolicy"]["syncOptions"]


def test_rejects_mutable_revision_and_sensitive_helm_values():
    with pytest.raises(ValueError, match="immutable"):
        _seat(revision="main")

    with pytest.raises(ValueError, match="sensitive"):
        build_workload_application(
            _seat(helm_values={"secrets": {"LLM_API_KEY": "sk-seat-secret"}})
        )

    with pytest.raises(ValueError, match="existing-Secret"):
        _seat(runtime_secret_value_path="secrets.LLM_API_KEY")


def test_runtime_secret_is_namespaced_labeled_and_separate_from_argocd():
    secret = build_runtime_secret(
        name="example-runtime",
        namespace="launchpad-seat-1",
        workshop_id="workshop-1",
        seat_id="seat-1",
        session_id="session-1",
        tenant_id="tenant-1",
        cluster_id="arena",
        string_data={
            "LLM_API_KEY": "sk-seat-secret",
            "LLM_BASE_URL": "https://models.example.com/v1",
            "LLM_MODEL": "granite",
        },
    )

    assert secret["metadata"]["namespace"] == "launchpad-seat-1"
    assert secret["metadata"]["labels"]["launchpad.redhat.com/seat-id"] == "seat-1"
    assert secret["metadata"]["labels"]["launchpad.redhat.com/session-id"] == ("session-1")
    assert secret["stringData"]["LLM_API_KEY"] == "sk-seat-secret"
    assert "data" not in secret


def test_cleanup_deletes_deterministic_workload_application():
    custom_objects = MagicMock()
    missing = Exception("not found")
    missing.status = 404
    custom_objects.get_namespaced_custom_object.side_effect = missing

    WorkloadGitOpsAdapter(custom_objects).delete_for_namespace("launchpad-seat-1")

    args = custom_objects.delete_namespaced_custom_object.call_args.args
    assert args[-1] == workload_application_name("launchpad-seat-1")


def test_runtime_secret_retry_preserves_existing_owned_credentials():
    from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter

    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._core_v1 = MagicMock()
    adapter._core_v1.create_namespaced_secret.side_effect = ApiException(status=409)
    adapter._core_v1.read_namespaced_secret.return_value = SimpleNamespace(
        metadata=SimpleNamespace(
            labels={
                "app.kubernetes.io/managed-by": "launchpad",
                "launchpad.redhat.com/workshop-id": "workshop-1",
                "launchpad.redhat.com/seat-id": "seat-1",
                "launchpad.redhat.com/session-id": "session-1",
            }
        )
    )
    secret = build_runtime_secret(
        name="example-runtime",
        namespace="launchpad-seat-1",
        workshop_id="workshop-1",
        seat_id="seat-1",
        session_id="session-1",
        tenant_id="tenant-1",
        cluster_id="arena",
        string_data={"POSTGRES_PASSWORD": "new-random-value"},
    )

    adapter._apply_workload_runtime_secret(secret)

    adapter._core_v1.patch_namespaced_secret.assert_not_called()


def test_runtime_secret_retry_refreshes_credentials_for_the_same_stable_seat():
    from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter

    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._core_v1 = MagicMock()
    adapter._core_v1.create_namespaced_secret.side_effect = ApiException(status=409)
    adapter._core_v1.read_namespaced_secret.return_value = SimpleNamespace(
        metadata=SimpleNamespace(
            labels={
                "app.kubernetes.io/managed-by": "launchpad",
                "launchpad.redhat.com/workshop-id": "workshop-1",
                "launchpad.redhat.com/seat-id": "seat-1",
                "launchpad.redhat.com/session-id": "previous-session",
            }
        )
    )
    secret = build_runtime_secret(
        name="example-runtime",
        namespace="launchpad-seat-1",
        workshop_id="workshop-1",
        seat_id="seat-1",
        session_id="replacement-session",
        tenant_id="tenant-1",
        cluster_id="arena",
        string_data={"POSTGRES_PASSWORD": "replacement-random-value"},
    )

    adapter._apply_workload_runtime_secret(secret)

    adapter._core_v1.patch_namespaced_secret.assert_called_once_with(
        "example-runtime",
        "launchpad-seat-1",
        body=secret,
    )


def test_runtime_secret_retry_rejects_a_secret_owned_by_another_seat():
    from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter

    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._core_v1 = MagicMock()
    adapter._core_v1.create_namespaced_secret.side_effect = ApiException(status=409)
    adapter._core_v1.read_namespaced_secret.return_value = SimpleNamespace(
        metadata=SimpleNamespace(
            labels={
                "app.kubernetes.io/managed-by": "launchpad",
                "launchpad.redhat.com/workshop-id": "workshop-1",
                "launchpad.redhat.com/seat-id": "different-seat",
                "launchpad.redhat.com/session-id": "previous-session",
            }
        )
    )
    secret = build_runtime_secret(
        name="example-runtime",
        namespace="launchpad-seat-1",
        workshop_id="workshop-1",
        seat_id="seat-1",
        session_id="session-1",
        tenant_id="tenant-1",
        cluster_id="arena",
        string_data={"POSTGRES_PASSWORD": "new-random-value"},
    )

    with pytest.raises(ValueError, match="owned by another seat"):
        adapter._apply_workload_runtime_secret(secret)


def test_private_workload_pull_secret_is_copied_without_entering_gitops(monkeypatch):
    from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter

    monkeypatch.setenv("LAUNCHPAD_CONTROL_NAMESPACE", "launchpad-control")
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._control_core_v1 = MagicMock()
    adapter._core_v1 = MagicMock()
    adapter._control_core_v1.read_namespaced_secret.return_value = SimpleNamespace(
        type="kubernetes.io/dockerconfigjson",
        data={".dockerconfigjson": "opaque-base64-config"},
    )
    labels = {
        "app.kubernetes.io/managed-by": "launchpad",
        "launchpad.redhat.com/session-id": "session-1",
    }

    adapter._copy_workload_image_pull_secret(
        "launchpad-registry-pull",
        target_namespace="launchpad-seat-1",
        labels=labels,
    )

    adapter._control_core_v1.read_namespaced_secret.assert_called_once_with(
        "launchpad-registry-pull", "launchpad-control"
    )
    body = adapter._core_v1.create_namespaced_secret.call_args.kwargs["body"]
    assert body["metadata"] == {
        "name": "launchpad-registry-pull",
        "namespace": "launchpad-seat-1",
        "labels": labels,
    }
    assert body["data"] == {".dockerconfigjson": "opaque-base64-config"}
def test_private_workload_pull_secret_fails_closed_when_source_is_missing(monkeypatch):
    from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter

    monkeypatch.setenv("LAUNCHPAD_CONTROL_NAMESPACE", "launchpad-control")
    adapter = OpenShiftProvisioningAdapter.__new__(OpenShiftProvisioningAdapter)
    adapter._control_core_v1 = MagicMock()
    adapter._core_v1 = MagicMock()
    adapter._control_core_v1.read_namespaced_secret.side_effect = ApiException(status=404)

    with pytest.raises(ValueError, match="image pull Secret.*unavailable"):
        adapter._copy_workload_image_pull_secret(
            "launchpad-registry-pull",
            target_namespace="launchpad-seat-1",
            labels={"app.kubernetes.io/managed-by": "launchpad"},
        )

    adapter._core_v1.create_namespaced_secret.assert_not_called()
