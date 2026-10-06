from types import SimpleNamespace

from app.adapters.openshift import participant_identity_cleanup as adapters


class Response:
    def __init__(self, body=None) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._body


def test_keycloak_adapter_disables_and_logs_out_exact_participant(monkeypatch) -> None:
    calls: list[tuple[str, str, object]] = []

    def post(url, **kwargs):
        calls.append(("POST", url, kwargs.get("data")))
        if url.endswith("/protocol/openid-connect/token"):
            return Response({"access_token": "not-logged"})
        return Response()

    def get(url, **kwargs):
        calls.append(("GET", url, kwargs.get("params")))
        return Response([{"id": "user-id", "username": "lp-person", "enabled": True}])

    def put(url, **kwargs):
        calls.append(("PUT", url, kwargs.get("json")))
        return Response()

    monkeypatch.setattr(adapters.httpx, "post", post)
    monkeypatch.setattr(adapters.httpx, "get", get)
    monkeypatch.setattr(adapters.httpx, "put", put)
    adapter = adapters.KeycloakParticipantIdentityAdapter(
        base_url="http://keycloak.test",
        realm="launchpad-public",
        client_id="reconciler",
        client_secret="not-logged",
    )

    assert adapter.disable_and_logout("lp-person") is True
    assert calls[1] == (
        "GET",
        "http://keycloak.test/admin/realms/launchpad-public/users",
        {"username": "lp-person", "exact": "true"},
    )
    assert calls[2][0] == "PUT"
    assert calls[2][2]["enabled"] is False
    assert calls[3][1].endswith("/users/user-id/logout")


def test_openshift_adapter_deletes_only_tokens_for_exact_username() -> None:
    api = SimpleNamespace()
    def list_cluster_custom_object(*, group, plural, **_kwargs):
        if group == "oauth.openshift.io" and plural == "oauthaccesstokens":
            return {
                "items": [
                    {"metadata": {"name": "token-a"}, "userName": "lp-person"},
                    {"metadata": {"name": "token-b"}, "userName": "someone-else"},
                    {"metadata": {"name": "token-c"}, "userName": "lp-person"},
                ]
            }
        if group == "user.openshift.io" and plural == "identities":
            return {
                "items": [
                    {
                        "metadata": {"name": "launchpad-public:participant-a"},
                        "user": {"name": "lp-person"},
                    },
                    {
                        "metadata": {"name": "launchpad-public:participant-b"},
                        "user": {"name": "someone-else"},
                    },
                ]
            }
        raise AssertionError(f"unexpected list: {group}/{plural}")

    api.list_cluster_custom_object = list_cluster_custom_object
    deletions: list[tuple[str, str]] = []

    def delete_cluster_custom_object(*, group, plural, name, **_kwargs):
        deletions.append((f"{group}/{plural}", name))

    api.delete_cluster_custom_object = delete_cluster_custom_object

    revoked, user_removed = adapters.OpenShiftParticipantIdentityAdapter(
        api
    ).revoke_tokens_and_user("lp-person")

    assert revoked == 2
    assert user_removed is True
    assert deletions == [
        ("oauth.openshift.io/oauthaccesstokens", "token-a"),
        ("oauth.openshift.io/oauthaccesstokens", "token-c"),
        ("user.openshift.io/identities", "launchpad-public:participant-a"),
        ("user.openshift.io/users", "lp-person"),
    ]
