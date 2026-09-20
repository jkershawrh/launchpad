from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.catalog_intake_discovery import CatalogIntakeSourceApproval

IMMUTABLE_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
CATALOG_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LabType = Literal["quick_start", "guided_build", "open_sandbox"]


class CatalogIntakeSubmission(BaseModel):
    """Admin request for a non-orderable repository intake draft."""

    model_config = ConfigDict(extra="forbid")

    catalog_item_id: str
    display_name: str
    repository_url: str
    revision: str
    owner: str
    audience: list[str]
    duration_hours: int = Field(ge=1, le=168)
    lab_type: LabType
    expected_scale: int = Field(ge=1, le=1000)

    @field_validator("catalog_item_id")
    @classmethod
    def catalog_id_is_safe(cls, value: str) -> str:
        if not CATALOG_ID.fullmatch(value):
            raise ValueError("catalog_item_id must be a DNS-safe kebab-case ID")
        return value

    @field_validator("display_name", "owner")
    @classmethod
    def required_text_is_not_blank(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("repository_url")
    @classmethod
    def repository_is_https_github(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or len([part for part in parsed.path.split("/") if part]) < 2
        ):
            raise ValueError("repository_url must be an HTTPS GitHub repository URL")
        return value.rstrip("/")

    @field_validator("revision")
    @classmethod
    def revision_is_immutable(cls, value: str) -> str:
        if not IMMUTABLE_GIT_SHA.fullmatch(value):
            raise ValueError("revision must be an immutable 40-character Git SHA")
        return value

    @field_validator("audience")
    @classmethod
    def audience_is_present(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if not normalized or any(not value for value in normalized):
            raise ValueError("audience must contain at least one non-empty value")
        return normalized


class CatalogIntakeDefaults(BaseModel):
    exposure_policies: list[str] = Field(default_factory=lambda: ["internal"])
    maximum_seats: int = 1


class CatalogIntakeEvidence(BaseModel):
    status: Literal["not-run", "partial"] = "not-run"
    artifacts: list[str] = Field(default_factory=list)
    required_gates: list[str] = Field(default_factory=list)


class CatalogIntakeReleaseIdentity(BaseModel):
    repository_url: str
    revision: str


class CatalogIntakeRollback(BaseModel):
    status: Literal["not-defined"] = "not-defined"
    metadata: dict[str, str] = Field(default_factory=dict)


class CatalogIntakeDiscoverySummary(BaseModel):
    status: Literal["passed"] = "passed"
    attempt_id: str
    output_hash: str
    worker_image_digest: str
    files_scanned: int = Field(ge=0)
    bytes_scanned: int = Field(ge=0)
    cleanup_verified: Literal[True] = True


class CatalogIntakeDiscoveryExecution(BaseModel):
    attempt_id: str
    state: Literal["queued", "running", "failed"]
    requested_by: str
    requested_at: datetime
    error_codes: list[str] = Field(default_factory=list)


class CatalogIntakeDraft(BaseModel):
    intake_id: str
    state: Literal["draft"] = "draft"
    orderable: Literal[False] = False
    promotion_eligible: Literal[False] = False
    storage_scope: Literal["process-local-draft", "durable-postgres"] = (
        "process-local-draft"
    )
    requested: CatalogIntakeSubmission
    defaults: CatalogIntakeDefaults = Field(default_factory=CatalogIntakeDefaults)
    blockers: list[str]
    evidence: CatalogIntakeEvidence
    supported_targets: list[str] = Field(default_factory=list)
    target_status: Literal["unverified"] = "unverified"
    release_identity: CatalogIntakeReleaseIdentity
    approval_history: list[dict[str, str]] = Field(default_factory=list)
    rollback: CatalogIntakeRollback = Field(default_factory=CatalogIntakeRollback)
    discovery: CatalogIntakeDiscoverySummary | None = None
    catalog_preview: dict[str, Any] | None = None
    source_approval: CatalogIntakeSourceApproval | None = None
    discovery_execution: CatalogIntakeDiscoveryExecution | None = None
