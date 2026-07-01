from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


@dataclass
class PlacementResource:
    name: str
    kind: str
    status: str
    namespace: Optional[str] = None
    ingress_domain: Optional[str] = None
    console_url: Optional[str] = None
    credentials: List[Dict[str, Any]] = field(default_factory=list)
    cluster_additional_vars: Dict[str, Any] = field(default_factory=dict)
    annotations: Dict[str, Any] = field(default_factory=dict)

    @property
    def sa_token(self) -> Optional[str]:
        for cred in self.credentials:
            if cred.get("kind") == "ServiceAccount":
                return cred.get("token")
        return None


@dataclass
class PlacementResult:
    service_uuid: str
    status: str
    resources: List[PlacementResource] = field(default_factory=list)


class SandboxAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Sandbox API error {status_code}: {message}")


class SandboxAPIClient:
    """Client for the RHDP Sandbox API (rhpds/sandbox)."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        login_token: Optional[str] = None,
    ):
        self.api_url = (api_url or os.environ.get("SANDBOX_API_URL", "")).rstrip("/")
        self._login_token = login_token or os.environ.get("SANDBOX_LOGIN_TOKEN", "")
        self._access_token: Optional[str] = None
        self._token_exp: Optional[float] = None
        self._session = _build_session()

    def _get_access_token(self) -> str:
        if self._access_token and self._token_exp and time.time() < self._token_exp:
            return self._access_token

        resp = self._session.get(
            f"{self.api_url}/api/v1/login",
            headers={"Authorization": f"Bearer {self._login_token}"},
            timeout=30,
            verify=True,
        )
        if resp.status_code != 200:
            raise SandboxAPIError(resp.status_code, "Login failed")

        data = resp.json()
        self._access_token = data["access_token"]
        self._token_exp = time.time() + 3500
        return self._access_token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.api_url}{path}"
        kwargs.setdefault("headers", self._headers())
        kwargs.setdefault("timeout", 30)
        kwargs.setdefault("verify", True)
        resp = self._session.request(method, url, **kwargs)
        return resp

    # ── Placements ────────────────────────────────────────────────

    def create_placement(
        self,
        service_uuid: str,
        resources: List[Dict[str, Any]],
        annotations: Optional[Dict[str, str]] = None,
    ) -> PlacementResult:
        payload = {
            "service_uuid": service_uuid,
            "resources": resources,
            "annotations": annotations or {},
        }
        resp = self._request("POST", "/api/v1/placements", json=payload)

        if resp.status_code == 404:
            data = resp.json()
            raise SandboxAPIError(404, data.get("message", "No matching cluster found"))

        if resp.status_code not in (200, 202):
            raise SandboxAPIError(resp.status_code, resp.text)

        data = resp.json()
        placement = data.get("Placement", data)
        return self._parse_placement(placement)

    def get_placement(self, service_uuid: str) -> PlacementResult:
        resp = self._request("GET", f"/api/v1/placements/{service_uuid}")
        if resp.status_code == 404:
            raise SandboxAPIError(404, f"Placement {service_uuid} not found")
        if resp.status_code != 200:
            raise SandboxAPIError(resp.status_code, resp.text)
        return self._parse_placement(resp.json())

    def wait_for_placement(
        self, service_uuid: str, timeout: int = 300, poll_interval: int = 5
    ) -> PlacementResult:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.get_placement(service_uuid)
            if result.status == "success":
                return result
            if result.status in ("error", "failed"):
                raise SandboxAPIError(500, f"Placement failed: {result.status}")
            time.sleep(poll_interval)
        raise SandboxAPIError(504, f"Placement {service_uuid} timed out after {timeout}s")

    def delete_placement(self, service_uuid: str) -> bool:
        resp = self._request("DELETE", f"/api/v1/placements/{service_uuid}")
        if resp.status_code == 202:
            return True
        if resp.status_code == 404:
            return True
        raise SandboxAPIError(resp.status_code, resp.text)

    def placement_action(self, service_uuid: str, action: str) -> None:
        resp = self._request("PUT", f"/api/v1/placements/{service_uuid}/{action}")
        if resp.status_code not in (200, 202):
            raise SandboxAPIError(resp.status_code, resp.text)

    # ── Cluster Configuration (admin) ─────────────────────────────

    def create_cluster_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._request(
            "POST", "/api/v1/ocp-shared-cluster-configurations", json=config
        )
        if resp.status_code != 201:
            raise SandboxAPIError(resp.status_code, resp.text)
        return resp.json()

    def get_cluster_config(self, name: str) -> Dict[str, Any]:
        resp = self._request("GET", f"/api/v1/ocp-shared-cluster-configurations/{name}")
        if resp.status_code != 200:
            raise SandboxAPIError(resp.status_code, resp.text)
        return resp.json()

    def update_cluster_config(self, name: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._request(
            "PUT", f"/api/v1/ocp-shared-cluster-configurations/{name}/update",
            json=updates,
        )
        if resp.status_code != 200:
            raise SandboxAPIError(resp.status_code, resp.text)
        return resp.json()

    def enable_cluster(self, name: str) -> None:
        resp = self._request("PUT", f"/api/v1/ocp-shared-cluster-configurations/{name}/enable")
        if resp.status_code != 200:
            raise SandboxAPIError(resp.status_code, resp.text)

    def disable_cluster(self, name: str) -> None:
        resp = self._request("PUT", f"/api/v1/ocp-shared-cluster-configurations/{name}/disable")
        if resp.status_code != 200:
            raise SandboxAPIError(resp.status_code, resp.text)

    def delete_cluster_config(self, name: str) -> None:
        resp = self._request("DELETE", f"/api/v1/ocp-shared-cluster-configurations/{name}")
        if resp.status_code not in (200, 404):
            raise SandboxAPIError(resp.status_code, resp.text)

    # ── Sandbox Accounts ──────────────────────────────────────────

    def list_sandboxes(self, service_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {}
        if service_uuid:
            params["service_uuid"] = service_uuid
        resp = self._request("GET", "/api/v1/accounts/OcpSandbox", params=params)
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise SandboxAPIError(resp.status_code, resp.text)
        return resp.json()

    def get_sandbox(self, name: str) -> Dict[str, Any]:
        resp = self._request("GET", f"/api/v1/accounts/OcpSandbox/{name}")
        if resp.status_code != 200:
            raise SandboxAPIError(resp.status_code, resp.text)
        return resp.json()

    # ── Helpers ───────────────────────────────────────────────────

    def _parse_placement(self, data: Dict[str, Any]) -> PlacementResult:
        resources = []
        for r in data.get("resources", []):
            resources.append(PlacementResource(
                name=r.get("name", ""),
                kind=r.get("kind", "OcpSandbox"),
                status=r.get("status", "unknown"),
                namespace=r.get("namespace"),
                ingress_domain=r.get("ingress_domain"),
                console_url=r.get("console_url"),
                credentials=r.get("credentials", []),
                cluster_additional_vars=r.get("cluster_additional_vars", {}),
                annotations=r.get("annotations", {}),
            ))
        return PlacementResult(
            service_uuid=data.get("service_uuid", ""),
            status=data.get("status", "unknown"),
            resources=resources,
        )
