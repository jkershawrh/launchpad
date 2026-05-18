from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

from app.adapters.interfaces import ProvisionResult
from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep

DEMOS_ROOT = Path(__file__).resolve().parents[4] / "demos"
COMPOSE_FILE = DEMOS_ROOT / "podman-compose.yaml"

GATEWAY_URL = "http://localhost:8080"
FRONTEND_URL = "http://localhost:3030"
HEALTH_TIMEOUT = 120
HEALTH_INTERVAL = 3


class LocalProvisioningAdapter:
    def __init__(self, compose_file: Optional[Path] = None):
        self._compose_file = compose_file or COMPOSE_FILE
        self._active_projects: dict[str, Path] = {}

    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan:
        demo_source = catalog_item.metadata.get("demo_source", "gateway")
        namespace = f"local-{request.tenant_id}-{uuid.uuid4().hex[:8]}"

        return ProvisioningPlan(
            request_id=request.request_id,
            target_namespace=namespace,
            steps=[
                ProvisioningStep(
                    name="start-postgres",
                    adapter="local",
                    action="podman_compose_up",
                    params={"service": "postgres"},
                    order=1,
                ),
                ProvisioningStep(
                    name="start-gateway",
                    adapter="local",
                    action="podman_compose_up",
                    params={"service": "gateway"},
                    order=2,
                ),
                ProvisioningStep(
                    name="start-cpu-inference",
                    adapter="local",
                    action="podman_compose_up",
                    params={"service": "cpu-inference"},
                    order=3,
                ),
                ProvisioningStep(
                    name="start-frontend",
                    adapter="local",
                    action="podman_compose_up",
                    params={"service": "frontend"},
                    order=4,
                ),
                ProvisioningStep(
                    name="wait-for-health",
                    adapter="local",
                    action="health_check",
                    params={"url": f"{GATEWAY_URL}/health", "timeout": HEALTH_TIMEOUT},
                    order=5,
                ),
            ],
            adapters_required=["local"],
            validation_steps=["gateway-health", "frontend-reachable"],
            estimated_duration="60s",
            required_resources={
                "demo_source": demo_source,
                "compose_file": str(self._compose_file),
            },
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        compose_file = plan.required_resources.get("compose_file", str(self._compose_file))

        if not Path(compose_file).exists():
            raise FileNotFoundError(f"Compose file not found: {compose_file}")

        result = subprocess.run(
            [sys.executable, "-m", "podman_compose", "-f", compose_file, "up", "-d"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path(compose_file).parent),
        )

        if result.returncode != 0:
            raise RuntimeError(f"podman-compose up failed:\n{result.stderr}")

        self._wait_for_health(f"{GATEWAY_URL}/health", HEALTH_TIMEOUT)

        namespace = plan.target_namespace or f"local-demo-{uuid.uuid4().hex[:8]}"
        self._active_projects[namespace] = Path(compose_file)

        return ProvisionResult(
            namespace=namespace,
            lab_url=FRONTEND_URL,
            dashboard_url=f"{GATEWAY_URL}/api/v1/requests",
            resources={
                "namespace": namespace,
                "compose_file": compose_file,
                "gateway_url": GATEWAY_URL,
                "frontend_url": FRONTEND_URL,
                "services": ["postgres", "gateway", "cpu-inference", "frontend"],
            },
        )

    def _wait_for_health(self, url: str, timeout: int) -> None:
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                resp = httpx.get(url, timeout=5)
                if resp.status_code == 200:
                    return
                last_error = f"status {resp.status_code}"
            except httpx.RequestError as e:
                last_error = str(e)
            time.sleep(HEALTH_INTERVAL)
        raise TimeoutError(f"Health check failed after {timeout}s: {last_error}")

    def get_compose_file(self, namespace: str) -> Optional[Path]:
        return self._active_projects.get(namespace)
