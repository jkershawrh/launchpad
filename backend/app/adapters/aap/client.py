from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("launchpad.aap")


class AAPError(Exception):
    pass


class AAPClient:
    """Client for Ansible Automation Platform controller API (v2).

    Launches job templates for provisioning, reclaim, and reset operations.
    Falls back to direct oc/helm if AAP is not configured.
    """

    def __init__(
        self,
        controller_url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.controller_url = (
            controller_url or os.environ.get("AAP_URL", "")
        ).rstrip("/")
        self._token = token or os.environ.get("AAP_TOKEN", "")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.controller_url}{path}"
        kwargs.setdefault("headers", self._headers())
        kwargs.setdefault("timeout", 30)
        kwargs.setdefault("verify", False)
        try:
            return requests.request(method, url, **kwargs)
        except Exception as e:
            raise AAPError(f"AAP request failed: {e}") from e

    def launch_job_template(
        self,
        template_name: str,
        extra_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        templates = self.list_job_templates()
        match = [t for t in templates if t["name"] == template_name]
        if not match:
            raise AAPError(f"Job template '{template_name}' not found")
        return self.launch_job_template_by_id(match[0]["id"], extra_vars)

    def launch_job_template_by_id(
        self,
        template_id: int,
        extra_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if extra_vars:
            payload["extra_vars"] = extra_vars

        resp = self._request(
            "POST",
            f"/api/v2/job_templates/{template_id}/launch/",
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise AAPError(f"Launch failed: {resp.status_code} {resp.text}")
        return resp.json()

    def get_job_status(self, job_id: int) -> Dict[str, Any]:
        resp = self._request("GET", f"/api/v2/jobs/{job_id}/")
        if resp.status_code != 200:
            raise AAPError(f"Get job failed: {resp.status_code}")
        return resp.json()

    def wait_for_job(
        self,
        job_id: int,
        timeout: int = 600,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.get_job_status(job_id)
            if status["status"] in ("successful", "failed", "error", "canceled"):
                return status
            time.sleep(poll_interval)
        raise AAPError(f"Job {job_id} timed out after {timeout}s")

    def list_job_templates(self) -> List[Dict[str, Any]]:
        resp = self._request("GET", "/api/v2/job_templates/")
        if resp.status_code != 200:
            raise AAPError(f"List templates failed: {resp.status_code}")
        return resp.json().get("results", [])
