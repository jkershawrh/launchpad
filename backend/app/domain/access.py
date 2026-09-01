from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ExposurePolicy(str, Enum):
    INTERNAL = "internal"
    PUBLIC_CODE = "public_code"


class EntitlementStatus(str, Enum):
    ACTIVE = "active"
    REAUTH_REQUIRED = "reauth_required"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AccessPolicy(BaseModel):
    policy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    order_type: str
    catalog_slug: str
    code_hash: str
    code_version: int = 1
    enabled: bool = True
    seat_refs: list[str]
    public_url: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def seat_limit(self) -> int:
        return len(self.seat_refs)


class ParticipantIdentity(BaseModel):
    participant_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    normalized_email: str
    keycloak_username: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    disabled_at: Optional[datetime] = None

    @field_validator("normalized_email")
    @classmethod
    def valid_email_shape(cls, value: str) -> str:
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("A valid email address is required")
        return value


class ParticipantEntitlement(BaseModel):
    entitlement_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    participant_id: str
    order_id: str
    seat_ref: str
    code_version: int
    status: EntitlementStatus = EntitlementStatus.ACTIVE
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AccessSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    token_hash: str
    participant_id: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    revoked_at: Optional[datetime] = None


class ClaimResult(BaseModel):
    identity: ParticipantIdentity
    entitlement: ParticipantEntitlement
    session_token: str
    public_url: str
