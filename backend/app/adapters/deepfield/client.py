from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from app.domain.orchestration import DeepFieldSignal

logger = logging.getLogger("launchpad.deepfield")


class DeepFieldAdapter:

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        ssl_verify: bool = True,
    ):
        self.api_url = (api_url or os.environ.get("DEEPFIELD_API_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("DEEPFIELD_API_KEY", "")
        self.ssl_verify = ssl_verify

    def get_cluster_signals(self, cluster_name: str) -> List[DeepFieldSignal]:
        if not self.api_url:
            return []
        try:
            headers = self._headers()
            with httpx.Client(verify=self.ssl_verify, timeout=10) as client:
                resp = client.get(
                    f"{self.api_url}/api/v1/clusters/{cluster_name}/signals",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json().get("signals", [])
                return [
                    DeepFieldSignal(
                        cluster_name=cluster_name,
                        metric_type=s.get("metric_type", "unknown"),
                        value=s.get("value", 0.0),
                        threshold=s.get("threshold", 0.0),
                        status=s.get("status", "normal"),
                    )
                    for s in data
                ]
        except Exception as e:
            logger.warning("DeepField signals unavailable for %s: %s", cluster_name, e)
            return []

    def get_fleet_overview(self) -> Dict[str, List[DeepFieldSignal]]:
        if not self.api_url:
            return {}
        try:
            headers = self._headers()
            with httpx.Client(verify=self.ssl_verify, timeout=10) as client:
                resp = client.get(
                    f"{self.api_url}/api/v1/fleet/overview",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json().get("clusters", {})
                result = {}
                for cluster_name, signals in data.items():
                    result[cluster_name] = [
                        DeepFieldSignal(
                            cluster_name=cluster_name,
                            metric_type=s.get("metric_type", "unknown"),
                            value=s.get("value", 0.0),
                            threshold=s.get("threshold", 0.0),
                            status=s.get("status", "normal"),
                        )
                        for s in signals
                    ]
                return result
        except Exception as e:
            logger.warning("DeepField fleet overview unavailable: %s", e)
            return {}

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers
