from unittest.mock import MagicMock

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
