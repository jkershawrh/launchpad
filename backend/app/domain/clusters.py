from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ClusterTarget(BaseModel):
    """A Launchpad execution target. Credentials are referenced, never embedded."""

    cluster_id: str
    display_name: str
    api_url: str = "https://kubernetes.default.svc"
    ingress_domain: str
    console_url: str = ""
    storage_class: str = "nfs-storage"
    credential_secret: Optional[str] = None
    enabled: bool = True
    local: bool = False
    priority: int = 100
    capabilities: List[str] = Field(default_factory=list)
    model_endpoints: Dict[str, str] = Field(default_factory=dict)
    public_access_enabled: bool = False
    public_ingress_domain: str = ""
    public_console_url: str = ""
    public_oauth_url: str = ""
    public_tls_secret: Optional[str] = None

    @field_validator("cluster_id")
    @classmethod
    def validate_cluster_id(cls, value: str) -> str:
        if not value or not value.replace("-", "").isalnum():
            raise ValueError("cluster_id must be a DNS-safe identifier")
        return value


class ClusterHealth(BaseModel):
    cluster_id: str
    display_name: str
    healthy: bool
    eligible: bool
    reason: str = ""
    available_cpu_millicores: int = 0
    available_memory_mib: int = 0
    available_pods: int = 0
    active_sessions: int = 0
    active_workshops: int = 0
    active_seats: int = 0
    reserved_cpu_millicores: int = 0
    reserved_memory_mib: int = 0
    reserved_pods: int = 0
