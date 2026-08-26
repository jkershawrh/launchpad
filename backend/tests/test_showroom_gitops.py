from unittest.mock import MagicMock

import pytest
import yaml

from app.adapters.openshift.showroom_gitops import (
    SHOWROOM_CHART,
    ShowroomGitOpsAdapter,
    ShowroomSeat,
    application_name,
    build_showroom_application,
)


def test_builds_official_chart_application_with_personalized_git_content():
    app = build_showroom_application(ShowroomSeat(
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
    ))

    assert app["spec"]["source"]["chart"] == SHOWROOM_CHART
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


def test_operator_workshop_uses_terminal_and_external_console_without_demo_workspace():
    app = build_showroom_application(ShowroomSeat(
        namespace="operator-seat-1", workshop_id="workshop-1", seat_id="seat-1",
        participant_id="user-1", workspace_url="",
        content_repo_url="https://github.com/jkershawrh/launchpad.git",
        content_ref="main", apps_domain="apps.example.com",
        console_url="https://console.example.com", journey="openshift-operators",
        cluster_display_name="Arena CPU Execution",
    ))
    values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
    ui = yaml.safe_load(values["content"]["uiConfig"])
    assert [tab["name"] for tab in ui["tabs"]] == ["Instructions", "Terminal"]
    user_data = yaml.safe_load(values["content"]["user_data"])
    assert user_data["openshift_console_url"] == "https://console.example.com"
    assert user_data["cluster_display_name"] == "Arena CPU Execution"
    assert values["terminal"]["storage"]["setup"] == "false"
    assert values["terminal"]["resources"]["requests"]["cpu"] == "100m"
    assert values["wetty"]["resources"]["requests"]["cpu"] == "50m"


def test_application_name_is_stable_dns_safe_and_bounded():
    name = application_name("Launchpad_Intel_" + "very-long-namespace-" * 6)
    assert len(name) <= 63
    assert name == application_name("Launchpad_Intel_" + "very-long-namespace-" * 6)
    assert name.replace("-", "").isalnum()


def test_content_revision_is_required():
    try:
        ShowroomSeat(
            namespace="lab", workshop_id="w", seat_id="s", participant_id="u",
            workspace_url="", content_repo_url="https://example/repo.git", content_ref="",
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
