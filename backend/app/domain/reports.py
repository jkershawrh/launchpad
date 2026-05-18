from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field


class HandoffPackage(BaseModel):
    lab_title: str
    tenant: str
    catalog_item: str
    session_id: str
    lab_url: Optional[str] = None
    dashboard_url: Optional[str] = None
    credentials_ref: Optional[str] = None
    maas_api_key: Optional[str] = None
    access_instructions: Optional[str] = None
    readme: Optional[str] = None
    expires_at: Optional[datetime] = None
    reset_instructions: Optional[str] = None
    support_contact: Optional[str] = None
    branding_metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = [
            f"# Your AI Lab is Ready",
            "",
            f"**Lab:** {self.lab_title}",
            f"**Tenant:** {self.tenant}",
            f"**Catalog Item:** {self.catalog_item}",
            f"**Session:** {self.session_id}",
            "",
        ]
        if self.lab_url:
            lines.append(f"**URL:** {self.lab_url}")
        if self.dashboard_url:
            lines.append(f"**Dashboard:** {self.dashboard_url}")
        if self.expires_at:
            lines.append(f"**Expires:** {self.expires_at.isoformat()}")
        if self.access_instructions:
            lines.extend(["", "## Access", self.access_instructions])
        if self.readme:
            lines.extend(["", "## Lab Guide", self.readme])
        if self.reset_instructions:
            lines.extend(["", "## Reset", self.reset_instructions])
        return "\n".join(lines)


class RepeatabilityReport(BaseModel):
    session_id: str
    catalog_item_id: str
    version: str
    request_hash: Optional[str] = None
    plan_hash: Optional[str] = None
    catalog_versioned: bool = False
    provisioning_plan_generated: bool = False
    validation_passed: bool = False
    handoff_generated: bool = False
    showback_generated: bool = False
    cleanup_defined: bool = False

    @computed_field
    @property
    def repeatability_score(self) -> int:
        score = 0
        if self.catalog_versioned:
            score += 20
        if self.provisioning_plan_generated:
            score += 20
        if self.validation_passed:
            score += 20
        if self.handoff_generated:
            score += 20
        if self.showback_generated:
            score += 10
        if self.cleanup_defined:
            score += 10
        return score


class SecurityPlan(BaseModel):
    namespace: str
    quota_profile: Optional[str] = None
    rbac_profile: Optional[str] = None
    network_policy_profile: Optional[str] = None
    secret_policy: Optional[str] = None
    egress_policy: Optional[str] = None
    notes: Optional[str] = None
    artifacts: List[str] = Field(default_factory=list)

    def planned_artifacts(self) -> List[str]:
        result = ["Namespace", "ServiceAccount"]
        if self.quota_profile:
            result.extend(["ResourceQuota", "LimitRange"])
        if self.rbac_profile:
            result.append("RoleBinding")
        if self.network_policy_profile:
            result.append("NetworkPolicy")
        return result
