from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IMMUTABLE_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class CatalogIntakeDiscoveryRequest(BaseModel):
    """Credential-free request consumed by one isolated discovery worker."""

    model_config = ConfigDict(extra="forbid")

    intake_id: str
    attempt_id: str
    repository_url: str
    revision: str
    catalog_item_id: str
    display_name: str
    policy_version: str
    source_approval_id: str
    worker_image_digest: str

    @field_validator(
        "intake_id", "attempt_id", "catalog_item_id", "source_approval_id"
    )
    @classmethod
    def identifiers_are_dns_safe(cls, value: str) -> str:
        if not SAFE_ID.fullmatch(value):
            raise ValueError("discovery identifiers must be DNS-safe")
        return value

    @field_validator("repository_url")
    @classmethod
    def repository_is_public_https_github(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or len([part for part in parsed.path.split("/") if part]) != 2
        ):
            raise ValueError("repository must be one public HTTPS GitHub repository")
        return value.rstrip("/")

    @field_validator("revision")
    @classmethod
    def revision_is_immutable(cls, value: str) -> str:
        if not IMMUTABLE_SHA.fullmatch(value):
            raise ValueError("revision must be a full 40-character Git commit SHA")
        return value

    @field_validator("display_name", "policy_version")
    @classmethod
    def text_is_present(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("discovery text fields cannot be blank")
        return normalized

    @field_validator("worker_image_digest")
    @classmethod
    def image_digest_is_immutable(cls, value: str) -> str:
        if not DIGEST.fullmatch(value):
            raise ValueError("worker_image_digest must be a SHA-256 digest")
        return value

    def idempotency_key(self) -> str:
        payload = self.model_dump(exclude={"attempt_id"}, mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


class CatalogIntakeSourceApproval(BaseModel):
    """Non-secret authorization record issued by the trusted intake controller."""

    model_config = ConfigDict(extra="forbid")

    approval_id: str
    repository_url: str
    revision: str
    requested_by: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    purpose: str

    @field_validator("approval_id")
    @classmethod
    def approval_id_is_safe(cls, value: str) -> str:
        if not SAFE_ID.fullmatch(value):
            raise ValueError("approval_id must be DNS-safe")
        return value

    @field_validator("repository_url")
    @classmethod
    def approval_repository_is_public_github(cls, value: str) -> str:
        return CatalogIntakeDiscoveryRequest.repository_is_public_https_github(value)

    @field_validator("revision")
    @classmethod
    def approval_revision_is_immutable(cls, value: str) -> str:
        return CatalogIntakeDiscoveryRequest.revision_is_immutable(value)

    @field_validator("requested_by", "approved_by", "purpose")
    @classmethod
    def approval_text_is_present(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source approval text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def approval_window_is_valid(self) -> CatalogIntakeSourceApproval:
        if self.requested_by == self.approved_by:
            raise ValueError("source approval requires separation of duties")
        if self.expires_at <= self.approved_at:
            raise ValueError("source approval must expire after it is issued")
        return self


class CatalogIntakeCleanupReceipt(BaseModel):
    receipt_id: str
    attempt_id: str
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    workspace_removed: bool
    process_count: int = 0
    bytes_removed: int = 0
    result: Literal["pass", "fail"]


class CatalogIntakeDiscoveryReceipt(BaseModel):
    schema_version: Literal["launchpad.redhat.com/catalog-intake-discovery-run/v1"] = (
        "launchpad.redhat.com/catalog-intake-discovery-run/v1"
    )
    intake_id: str
    attempt_id: str
    idempotency_key: str
    repository_url: str
    revision: str
    policy_version: str
    source_approval_id: str
    worker_image_digest: str
    started_at: datetime
    finished_at: datetime
    status: Literal["passed", "denied", "failed"]
    error_codes: list[str] = Field(default_factory=list)
    scan_summary: dict[str, int]
    output_hash: str | None = None
    draft_intake: dict[str, Any] | None = None
    cleanup: CatalogIntakeCleanupReceipt
