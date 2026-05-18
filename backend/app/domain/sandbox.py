from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import AAPLevel, AccessMethod, GaudiMode, StackLevel

STACK_PACKAGES: Dict[str, List[str]] = {
    "minimal": ["python3.11", "oc", "podman", "git", "vim"],
    "ai_dev": [
        "python3.11", "oc", "podman", "git", "vim",
        "pytorch", "vllm", "jupyter", "ansible-navigator",
        "huggingface-cli", "sample-notebooks",
    ],
    "full_redhat_ai": [
        "python3.11", "oc", "podman", "git", "vim",
        "pytorch", "vllm", "jupyter", "ansible-navigator",
        "huggingface-cli", "sample-notebooks",
        "openvino", "intel-extension-for-pytorch", "intel-oneapi",
        "kafka-client", "tekton-cli", "helm", "kustomize",
    ],
}

ACCESS_PORTS: Dict[str, int] = {
    "web_console": 6901,
    "ssh": 2222,
    "vscode": 8443,
    "jupyter": 8888,
    "api": 8080,
}


class SandboxProfile(BaseModel):
    sandbox_profile_id: str
    display_name: str
    base_image: str = "ubi9-python"
    stack_level: StackLevel = StackLevel.MINIMAL
    access_methods: List[AccessMethod] = Field(
        default_factory=lambda: [AccessMethod.WEB_CONSOLE, AccessMethod.SSH]
    )
    aap_level: AAPLevel = AAPLevel.NONE
    gpu_access: GaudiMode = GaudiMode.NONE
    storage_size: str = "20Gi"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("sandbox_profile_id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("sandbox_profile_id must not be empty")
        return v

    @property
    def packages(self) -> List[str]:
        return STACK_PACKAGES.get(self.stack_level.value, STACK_PACKAGES["minimal"])

    @property
    def ports(self) -> Dict[str, int]:
        return {m.value: ACCESS_PORTS[m.value] for m in self.access_methods}


class SandboxConnectionInfo(BaseModel):
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: str = "lab-user"
    ssh_password: Optional[str] = None
    web_console_url: Optional[str] = None
    vscode_url: Optional[str] = None
    jupyter_url: Optional[str] = None
    api_url: Optional[str] = None
    aap_url: Optional[str] = None
