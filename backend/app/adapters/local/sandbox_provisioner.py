from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict


from app.adapters.interfaces import ProvisionResult
from app.domain.models import CatalogItem, LabRequest, ProvisioningPlan, ProvisioningStep

SANDBOX_DIR = Path(__file__).resolve().parents[4] / "demos" / "containers" / "sandbox"
SANDBOX_IMAGE = "launchpad-sandbox"

ACCESS_PORTS = {
    "ssh": 2222,
    "jupyter": 8888,
    "vscode": 8443,
    "web_console": 6901,
    "api": 8080,
}


class LocalSandboxProvisioner:
    def __init__(self) -> None:
        self._active_containers: Dict[str, str] = {}

    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan:
        sandbox_meta = catalog_item.metadata or {}
        stack_level = (request.metadata or {}).get("stack_level") or sandbox_meta.get("stack_level", "minimal")
        access_methods = (request.metadata or {}).get("access_methods") or sandbox_meta.get("access_methods", ["ssh"])

        container_name = f"sandbox-{request.tenant_id}-{uuid.uuid4().hex[:8]}"

        return ProvisioningPlan(
            request_id=request.request_id,
            target_namespace=container_name,
            steps=[
                ProvisioningStep(
                    name="build-sandbox-image",
                    adapter="local-sandbox",
                    action="build",
                    params={"context": str(SANDBOX_DIR), "image": SANDBOX_IMAGE},
                    order=1,
                ),
                ProvisioningStep(
                    name="start-sandbox-container",
                    adapter="local-sandbox",
                    action="run",
                    params={
                        "container_name": container_name,
                        "stack_level": stack_level,
                        "access_methods": access_methods,
                    },
                    order=2,
                ),
                ProvisioningStep(
                    name="wait-for-ssh",
                    adapter="local-sandbox",
                    action="health_check",
                    params={"port": 2222, "timeout": 60},
                    order=3,
                ),
            ],
            adapters_required=["local-sandbox"],
            validation_steps=["ssh-check"],
            estimated_duration="30s",
            required_resources={
                "sandbox_type": sandbox_meta.get("sandbox_type", "custom"),
                "stack_level": stack_level,
                "access_methods": access_methods,
                "container_name": container_name,
            },
        )

    def provision(self, plan: ProvisioningPlan) -> ProvisionResult:
        container_name = plan.required_resources.get("container_name", plan.target_namespace)
        stack_level = plan.required_resources.get("stack_level", "minimal")
        access_methods = plan.required_resources.get("access_methods", ["ssh"])

        self._build_image()

        port_args = []
        for method in access_methods:
            if method in ACCESS_PORTS:
                port = ACCESS_PORTS[method]
                port_args.extend(["-p", f"{port}:{port}"])
        if not port_args:
            port_args = ["-p", "2222:2222"]

        result = subprocess.run(
            [
                "/opt/podman/bin/podman", "run", "-d",
                "--name", container_name,
                "-e", f"STACK_LEVEL={stack_level}",
                *port_args,
                SANDBOX_IMAGE,
            ],
            capture_output=True, text=True, timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to start sandbox:\n{result.stderr}")

        self._active_containers[container_name] = container_name
        self._wait_for_ssh(2222, timeout=60)

        connection_info = {"ssh": "ssh lab-user@localhost -p 2222"}
        lab_url = "ssh://lab-user@localhost:2222"

        if "jupyter" in access_methods:
            connection_info["jupyter"] = "http://localhost:8888"
        if "vscode" in access_methods:
            connection_info["vscode"] = "http://localhost:8443"
        if "web_console" in access_methods:
            connection_info["web_console"] = "http://localhost:6901"
            lab_url = "http://localhost:6901"

        return ProvisionResult(
            namespace=container_name,
            lab_url=lab_url,
            dashboard_url="http://localhost:8080",
            resources={
                "namespace": container_name,
                "container_name": container_name,
                "sandbox_type": plan.required_resources.get("sandbox_type", "custom"),
                "stack_level": stack_level,
                "access_methods": access_methods,
                "connection_info": connection_info,
            },
        )

    def _build_image(self) -> None:
        result = subprocess.run(
            ["/opt/podman/bin/podman", "build", "-t", SANDBOX_IMAGE, str(SANDBOX_DIR)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to build sandbox image:\n{result.stderr}")

    def _wait_for_ssh(self, port: int, timeout: int = 60) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect(("localhost", port))
                sock.close()
                return
            except (ConnectionRefusedError, OSError):
                time.sleep(2)
        raise TimeoutError(f"SSH not ready on port {port} after {timeout}s")

    def cleanup(self, container_name: str) -> bool:
        result = subprocess.run(
            ["/opt/podman/bin/podman", "rm", "-f", container_name],
            capture_output=True, text=True, timeout=30,
        )
        self._active_containers.pop(container_name, None)
        return result.returncode == 0
