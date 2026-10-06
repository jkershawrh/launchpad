from __future__ import annotations

import httpx
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


class KeycloakParticipantIdentityAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds

    def _admin_token(self) -> str:
        response = httpx.post(
            f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return str(response.json()["access_token"])

    def disable_and_logout(self, username: str) -> bool:
        token = self._admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = httpx.get(
            f"{self.base_url}/admin/realms/{self.realm}/users",
            params={"username": username, "exact": "true"},
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        users = [item for item in response.json() if item.get("username") == username]
        if not users:
            return False
        user_id = str(users[0]["id"])
        update = httpx.put(
            f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}",
            json={**users[0], "enabled": False},
            headers=headers,
            timeout=self.timeout_seconds,
        )
        update.raise_for_status()
        logout = httpx.post(
            f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/logout",
            headers=headers,
            timeout=self.timeout_seconds,
        )
        logout.raise_for_status()
        return True


class OpenShiftParticipantIdentityAdapter:
    def __init__(self, api: client.CustomObjectsApi | None = None) -> None:
        if api is None:
            config.load_incluster_config()
            api = client.CustomObjectsApi()
        self.api = api

    def revoke_tokens_and_user(self, username: str) -> tuple[int, bool]:
        response = self.api.list_cluster_custom_object(
            group="oauth.openshift.io",
            version="v1",
            plural="oauthaccesstokens",
        )
        matching = [item for item in response.get("items", []) if item.get("userName") == username]
        for item in matching:
            self.api.delete_cluster_custom_object(
                group="oauth.openshift.io",
                version="v1",
                plural="oauthaccesstokens",
                name=item["metadata"]["name"],
            )

        user_removed = False
        try:
            self.api.delete_cluster_custom_object(
                group="user.openshift.io",
                version="v1",
                plural="users",
                name=username,
            )
            user_removed = True
        except ApiException as exc:
            if exc.status != 404:
                raise
        return len(matching), user_removed
