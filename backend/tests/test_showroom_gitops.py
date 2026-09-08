from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from app.adapters.openshift.showroom_gitops import (
    SHOWROOM_CHART,
    SHOWROOM_GIT_CLONER_IMAGE,
    ShowroomGitOpsAdapter,
    ShowroomSeat,
    ShowroomToolTab,
    application_name,
    build_showroom_application,
)

ROOT = Path(__file__).resolve().parents[2]


def test_showroom_uses_immutable_git_cloner_that_marks_repo_safe_before_entering_it():
    image_dir = ROOT / "workshop-images/showroom-git-cloner"
    entrypoint = (image_dir / "entrypoint.sh").read_text()

    assert SHOWROOM_GIT_CLONER_IMAGE.startswith(
        "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/"
        "launchpad-showroom-git-cloner@sha256:"
    )
    assert entrypoint.index('git config --global --add safe.directory "${CLONE_DIR}"') < (
        entrypoint.index('cd "${CLONE_DIR}"')
    )

    app = build_showroom_application(
        ShowroomSeat(
            namespace="launchpad-seat-agentops-1",
            workshop_id="workshop-1",
            seat_id="seat-1",
            participant_id="lp-user-1",
            workspace_url="",
            content_repo_url="https://github.com/example/showroom.git",
            content_ref="b" * 40,
            apps_domain="apps.arena.example.com",
        )
    )
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    assert values["git_cloner"]["image"] == SHOWROOM_GIT_CLONER_IMAGE


def test_showroom_uses_cluster_specific_immutable_support_images():
    terminal_image = "registry.example.test/showroom-terminal@sha256:" + "a" * 64
    git_cloner_image = "registry.example.test/showroom-git-cloner@sha256:" + "b" * 64

    app = build_showroom_application(
        ShowroomSeat(
            namespace="launchpad-seat-remote-1",
            workshop_id="workshop-1",
            seat_id="seat-1",
            participant_id="lp-user-1",
            workspace_url="",
            content_repo_url="https://github.com/example/showroom.git",
            content_ref="c" * 40,
            apps_domain="apps.remote.example.com",
            terminal_image=terminal_image,
            git_cloner_image=git_cloner_image,
        )
    )

    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    assert values["terminal"]["image"] == terminal_image
    assert values["git_cloner"]["image"] == git_cloner_image


def test_builds_official_chart_application_with_personalized_git_content():
    app = build_showroom_application(
        ShowroomSeat(
            namespace="launchpad-intel-guided-rag-123456",
            workshop_id="workshop-1",
            seat_id="seat-07",
            participant_id="intel-user-07",
            workspace_url="https://demo.apps.example.com/rag",
            content_repo_url="https://github.com/jkershawrh/launchpad.git",
            content_ref="327da5a",
            apps_domain="apps.example.com",
            console_url="https://console-openshift-console.apps.example.com",
            journey="guided-rag",
            session_id="session-1",
            tenant_id="tenant-1",
        )
    )

    assert app["spec"]["source"]["chart"] == SHOWROOM_CHART
    assert app["metadata"]["labels"]["launchpad.redhat.com/session-id"] == ("session-1")
    assert app["metadata"]["labels"]["launchpad.redhat.com/tenant"] == "tenant-1"
    assert app["spec"]["syncPolicy"]["automated"] == {"prune": True, "selfHeal": True}
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    assert values["content"]["repoRef"] == "327da5a"
    assert values["terminal"]["storage"]["storageClass"] == "nfs-storage"
    assert values["content"]["repoUrl"].endswith("launchpad.git")
    user_data = yaml.safe_load(values["content"]["user_data"])
    assert user_data["workshop_id"] == "workshop-1"
    assert user_data["seat_id"] == "seat-07"
    assert user_data["showroom_journey"] == "guided-rag"
    assert user_data["workspace_url"].endswith("/rag")
    ui = yaml.safe_load(values["content"]["uiConfig"])
    assert any(tab.get("name") == "RAG Workspace" for tab in ui["tabs"])


def test_showroom_application_uses_background_cascade_for_bounded_reclaim():
    app = build_showroom_application(
        ShowroomSeat(
            namespace="launchpad-seat-cleanup-1",
            workshop_id="workshop-cleanup-1",
            seat_id="seat-cleanup-1",
            participant_id="participant-cleanup-1",
            workspace_url="https://workspace.example.com",
            content_repo_url="https://github.com/rhpds/launchpad.git",
            content_ref="a" * 40,
            apps_domain="apps.arena.example.com",
        )
    )

    assert app["metadata"]["finalizers"] == ["resources-finalizer.argocd.argoproj.io/background"]


def test_operator_workshop_places_namespace_console_inside_showroom():
    app = build_showroom_application(
        ShowroomSeat(
            namespace="operator-seat-1",
            workshop_id="workshop-1",
            seat_id="seat-1",
            participant_id="user-1",
            workspace_url="",
            content_repo_url="https://github.com/jkershawrh/launchpad.git",
            content_ref="main",
            apps_domain="apps.example.com",
            console_url="https://console.example.com",
            journey="openshift-operators",
            cluster_display_name="Arena CPU Execution",
        )
    )
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    ui = yaml.safe_load(values["content"]["uiConfig"])
    assert [tab["name"] for tab in ui["tabs"]] == [
        "Terminal",
        "OpenShift Console",
    ]
    assert ui["persist_url_state"] is False
    assert ui["tabs"][-1]["url"] == "https://console.example.com"
    user_data = yaml.safe_load(values["content"]["user_data"])
    assert user_data["openshift_console_url"] == "https://console.example.com"
    assert user_data["cluster_display_name"] == "Arena CPU Execution"
    assert values["terminal"]["storage"]["setup"] == "false"
    assert values["terminal"]["resources"]["requests"]["cpu"] == "100m"
    assert values["terminal"]["image"] == (
        "image-registry.openshift-image-registry.svc:5000/partner-ai-launchpad/"
        "launchpad-showroom-terminal@sha256:"
        "164aa93d20af95dc916aa695556a1cae2ec057385ee1b254157df9eead099d9b"
    )
    assert values["wetty"]["setup"] == "false"


def test_launchpad_terminal_defaults_oc_to_its_rotating_seat_identity():
    image_dir = ROOT / "workshop-images/showroom-terminal"
    containerfile = (image_dir / "Containerfile").read_text()
    entrypoint = (image_dir / "launchpad-runttyd").read_text()

    assert (
        "@sha256:606317dc396db33b879c1d3807844990cd37bb0c787b0b525edbeb70283b5350" in containerfile
    )
    assert "tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token" in entrypoint
    assert "namespace: ${NAMESPACE}" in entrypoint
    assert 'KUBECONFIG="${HOME}/.kube/config"' in entrypoint
    assert "launchpad-participant-runtime" in entrypoint
    assert 'export MAAS_API_KEY="$(read_runtime_value MAAS_API_KEY)"' in entrypoint


def test_launchpad_terminal_relaxes_home_permissions_before_persistent_volume_reclaim():
    entrypoint = (ROOT / "workshop-images/showroom-terminal/launchpad-runttyd").read_text()

    assert "cleanup_home_for_reclaim" in entrypoint
    assert 'chmod -R a+rwX "${HOME}"' in entrypoint
    assert "trap cleanup_home_for_reclaim EXIT" in entrypoint


def test_ephemeral_showroom_terminal_does_not_allocate_nfs_storage():
    app = build_showroom_application(
        ShowroomSeat(
            namespace="launchpad-agentops-seat-1",
            workshop_id="workshop-1",
            seat_id="seat-1",
            participant_id="participant-1",
            workspace_url="https://app.example.com",
            content_repo_url="https://github.com/rhpds/launchpad.git",
            content_ref="a" * 40,
            apps_domain="apps.arena.example.com",
            terminal_storage_enabled=False,
        )
    )

    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])

    assert values["terminal"]["storage"] == {"setup": "false"}


def test_content_lab_receives_launchpad_runtime_values_and_named_workspace_tab():
    app = build_showroom_application(
        ShowroomSeat(
            namespace="launchpad-seat-agent-1",
            workshop_id="workshop-1",
            seat_id="seat-1",
            participant_id="lp-user-1",
            workspace_url="https://solution-ui-launchpad-seat-agent-1.apps.example.com",
            workspace_title="Solution Architect",
            content_repo_url="https://github.com/rhpds/launchpad.git",
            content_ref="main",
            content_playbook="site-intel-xeon6-agent-201.yml",
            apps_domain="apps.example.com",
            console_url="https://console.example.com/k8s/ns/launchpad-seat-agent-1",
            openshift_api_url="https://api.example.com:6443",
            maas_endpoint="https://models.example.com",
            maas_api_key="sk-seat-1",
            maas_model="granite-2b-cpu",
            journey="intel-xeon6-agent-201",
            content_only=True,
        )
    )

    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    ui = yaml.safe_load(values["content"]["uiConfig"])
    assert [tab["name"] for tab in ui["tabs"]] == [
        "Terminal",
        "Solution Architect",
        "OpenShift Console",
    ]
    user_data = yaml.safe_load(values["content"]["user_data"])
    assert user_data["namespace"] == "launchpad-seat-agent-1"
    assert user_data["project_name"] == "launchpad-seat-agent-1"
    assert user_data["openshift_api_url"] == "https://api.example.com:6443"
    assert user_data["openshift_cluster_ingress_domain"] == "apps.example.com"
    assert user_data["maas_endpoint"] == "https://models.example.com"
    assert user_data["maas_url"] == "https://models.example.com"
    assert user_data["maas_api_url"] == "https://models.example.com/v1"
    assert "maas_api_key" not in user_data
    assert "litellm_api_key" not in user_data
    assert "sk-seat-1" not in app["spec"]["source"]["helm"]["values"]
    assert user_data["maas_model"] == "granite-2b-cpu"
    assert values["terminal"]["storage"]["setup"] == "false"


def test_declared_tool_tabs_replace_the_legacy_three_tab_layout_in_order():
    app = build_showroom_application(
        ShowroomSeat(
            namespace="launchpad-seat-agentops-1",
            workshop_id="workshop-1",
            seat_id="seat-1",
            participant_id="lp-user-1",
            workspace_url="",
            content_repo_url="https://github.com/example/showroom.git",
            content_ref="b" * 40,
            apps_domain="apps.arena.example.com",
            tool_tabs=(
                ShowroomToolTab(name="OpenShift Console", url="https://console.example.com"),
                ShowroomToolTab(name="Terminal", path="/terminal", port=443),
                ShowroomToolTab(name="Mortgage AI App", url="https://mortgage.example.com"),
                ShowroomToolTab(name="Grafana", url="https://grafana.example.com"),
            ),
        )
    )

    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    ui = yaml.safe_load(values["content"]["uiConfig"])
    assert ui["tabs"] == [
        {"name": "OpenShift Console", "url": "https://console.example.com"},
        {"name": "Terminal", "path": "/terminal", "port": 443},
        {"name": "Mortgage AI App", "url": "https://mortgage.example.com"},
        {"name": "Grafana", "url": "https://grafana.example.com"},
    ]


def test_application_name_is_stable_dns_safe_and_bounded():
    name = application_name("Launchpad_Intel_" + "very-long-namespace-" * 6)
    assert len(name) <= 63
    assert name == application_name("Launchpad_Intel_" + "very-long-namespace-" * 6)
    assert name.replace("-", "").isalnum()


def test_content_revision_is_required():
    try:
        ShowroomSeat(
            namespace="lab",
            workshop_id="w",
            seat_id="s",
            participant_id="u",
            workspace_url="",
            content_repo_url="https://example/repo.git",
            content_ref="",
            apps_domain="apps.example.com",
        )
    except ValueError as exc:
        assert "content_ref" in str(exc)
    else:
        raise AssertionError("empty content refs must fail")


def test_cleanup_deletes_stable_argocd_application_before_namespace():
    custom_objects = MagicMock()
    missing = Exception("not found")
    missing.status = 404
    custom_objects.get_namespaced_custom_object.side_effect = missing
    ShowroomGitOpsAdapter(custom_objects).delete_for_namespace("launchpad-seat-123")
    args = custom_objects.delete_namespaced_custom_object.call_args.args
    assert args[-1] == application_name("launchpad-seat-123")


def test_cleanup_waits_until_argocd_application_is_gone(monkeypatch):
    custom_objects = MagicMock()
    missing = Exception("not found")
    missing.status = 404
    custom_objects.get_namespaced_custom_object.side_effect = [
        {"metadata": {"deletionTimestamp": "now"}},
        missing,
    ]
    monkeypatch.setattr("app.adapters.openshift.showroom_gitops.time.sleep", lambda _: None)

    ShowroomGitOpsAdapter(custom_objects).delete_for_namespace("lab")

    assert custom_objects.get_namespaced_custom_object.call_count == 2


def test_cleanup_recovers_stale_finalizer_only_for_owned_deleting_application(monkeypatch):
    custom_objects = MagicMock()
    custom_objects.get_namespaced_custom_object.return_value = {
        "metadata": {
            "deletionTimestamp": "now",
            "labels": {"app.kubernetes.io/managed-by": "launchpad"},
            "finalizers": ["resources-finalizer.argocd.argoproj.io"],
        },
        "spec": {"destination": {"namespace": "lab"}},
    }
    monkeypatch.setattr("app.adapters.openshift.showroom_gitops.time.sleep", lambda _: None)

    ShowroomGitOpsAdapter(custom_objects).delete_for_namespace("lab", timeout=0)

    patch = custom_objects.patch_namespaced_custom_object.call_args.args
    assert patch[-1] == {"metadata": {"finalizers": []}}


def test_cleanup_does_not_force_finalizer_for_unowned_application(monkeypatch):
    custom_objects = MagicMock()
    custom_objects.get_namespaced_custom_object.return_value = {
        "metadata": {
            "deletionTimestamp": "now",
            "labels": {"app.kubernetes.io/managed-by": "someone-else"},
        },
        "spec": {"destination": {"namespace": "lab"}},
    }
    monkeypatch.setattr("app.adapters.openshift.showroom_gitops.time.sleep", lambda _: None)

    with pytest.raises(TimeoutError):
        ShowroomGitOpsAdapter(custom_objects).delete_for_namespace("lab", timeout=0)

    custom_objects.patch_namespaced_custom_object.assert_not_called()
