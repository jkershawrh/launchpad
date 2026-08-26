from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import (
    BrandingTheme,
    CatalogCategory,
    CatalogStatus,
    GaudiMode,
    LabRequestStatus,
    Persistence,
    SessionStatus,
    TenantStatus,
    TenantType,
    ValidationResultStatus,
    WorkshopSeatStatus,
    WorkshopStatus,
)


class Tenant(BaseModel):
    tenant_id: str
    display_name: str
    tenant_type: TenantType
    status: TenantStatus = TenantStatus.ACTIVE
    branding_profile_id: Optional[str] = None
    default_quota_profile: Optional[str] = None
    default_ttl: Optional[str] = None
    cost_center: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("tenant_id")
    @classmethod
    def tenant_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("tenant_id must not be empty")
        return v

    @field_validator("display_name")
    @classmethod
    def display_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("display_name must not be empty")
        return v


class CatalogItem(BaseModel):
    catalog_item_id: str
    display_name: str
    description: str = ""
    category: CatalogCategory
    version: str = "1.0.0"
    status: CatalogStatus = CatalogStatus.DRAFT
    required_capabilities: List[str] = Field(default_factory=list)
    optional_capabilities: List[str] = Field(default_factory=list)
    default_hardware_profile: Optional[str] = None
    default_quota_profile: Optional[str] = None
    default_ttl: Optional[str] = None
    provisioner_refs: List[str] = Field(default_factory=list)
    validation_refs: List[str] = Field(default_factory=list)
    observability_profile: Optional[str] = None
    supported_branding: List[str] = Field(default_factory=list)
    handoff_template: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("catalog_item_id")
    @classmethod
    def catalog_item_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("catalog_item_id must not be empty")
        return v


class LabRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    requester_id: str
    catalog_item_id: str
    requested_mode: CatalogCategory
    persistence: Persistence = Persistence.EPHEMERAL
    ttl: Optional[str] = None
    hardware_profile: Optional[str] = None
    quota_profile: Optional[str] = None
    branding_profile_id: Optional[str] = None
    requested_capabilities: List[str] = Field(default_factory=list)
    requested_models: List[str] = Field(default_factory=list)
    status: LabRequestStatus = LabRequestStatus.SUBMITTED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("tenant_id", "requester_id", "catalog_item_id")
    @classmethod
    def required_ids_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be empty")
        return v

    @field_validator("requested_models")
    @classmethod
    def requested_models_are_unique_and_non_empty(cls, values: List[str]) -> List[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("requested model IDs must not be empty")
        return list(dict.fromkeys(normalized))


class ValidationResult(BaseModel):
    validation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    check_name: str
    result: ValidationResultStatus
    message: Optional[str] = None
    evidence: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LifecycleEvent(BaseModel):
    from_status: SessionStatus
    to_status: SessionStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    reason: Optional[str] = None


class LabSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    tenant_id: str
    catalog_item_id: str
    namespace: Optional[str] = None
    cluster_ref: Optional[str] = None
    status: SessionStatus = SessionStatus.REQUESTED
    lab_url: Optional[str] = None
    dashboard_url: Optional[str] = None
    handoff_url: Optional[str] = None
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    resources: Dict[str, Any] = Field(default_factory=dict)
    validation_results: List[ValidationResult] = Field(default_factory=list)
    showback_ref: Optional[str] = None
    maas_api_key: Optional[str] = None
    lifecycle_events: List[LifecycleEvent] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HardwareProfile(BaseModel):
    hardware_profile_id: str
    display_name: str
    xeon_required: bool = True
    gaudi_mode: GaudiMode = GaudiMode.NONE
    openshift_ai_required: bool = False
    kafka_required: bool = False
    virtualization_required: bool = False
    notes: Optional[str] = None

    @field_validator("hardware_profile_id")
    @classmethod
    def hardware_profile_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("hardware_profile_id must not be empty")
        return v


class QuotaProfile(BaseModel):
    quota_profile_id: str
    cpu_limit: str
    memory_limit: str
    storage_limit: str
    max_pods: int
    max_routes: int
    gaudi_access_limit: Optional[int] = None
    ttl_max: Optional[str] = None

    @field_validator("max_pods", "max_routes")
    @classmethod
    def positive_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be at least 1")
        return v


class BrandingProfile(BaseModel):
    branding_profile_id: str
    display_name: str
    title: str
    logo_refs: List[str] = Field(default_factory=list)
    primary_color: str = "#EE0000"
    secondary_color: str = "#0066CC"
    footer_text: Optional[str] = None
    theme: BrandingTheme = BrandingTheme.DEFAULT
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("branding_profile_id")
    @classmethod
    def branding_profile_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("branding_profile_id must not be empty")
        return v


class ProvisioningStep(BaseModel):
    name: str
    adapter: str
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    order: int = 0


class ProvisioningPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    steps: List[ProvisioningStep] = Field(default_factory=list)
    target_namespace: Optional[str] = None
    target_cluster: Optional[str] = None
    required_resources: Dict[str, Any] = Field(default_factory=dict)
    adapters_required: List[str] = Field(default_factory=list)
    validation_steps: List[str] = Field(default_factory=list)
    estimated_duration: Optional[str] = None
    status: str = "pending"


class ShowbackRecord(BaseModel):
    showback_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    session_id: str
    catalog_item_id: str
    namespace: Optional[str] = None
    duration_seconds: int = 0
    cpu_requested: Optional[str] = None
    cpu_used_estimate: Optional[str] = None
    memory_requested: Optional[str] = None
    memory_used_estimate: Optional[str] = None
    storage_requested: Optional[str] = None
    storage_used_estimate: Optional[str] = None
    gaudi_endpoint_requests: int = 0
    gaudi_direct_minutes: int = 0
    model_requests: int = 0
    estimated_tokens: int = 0
    kafka_messages: int = 0
    cost_estimate: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkshopSeat(BaseModel):
    seat_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workshop_id: str
    seat_number: int = Field(ge=1)
    participant_id: Optional[str] = None
    status: WorkshopSeatStatus = WorkshopSeatStatus.PENDING
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    lab_url: Optional[str] = None
    showroom_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Workshop(BaseModel):
    workshop_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    catalog_item_id: str
    num_users: int = Field(ge=1, le=100)
    name: Optional[str] = None
    owner_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    order_fingerprint: Optional[str] = None
    ttl: str = "8h"
    ocp_version: str = "4.20"
    purpose: str = "events"
    status: WorkshopStatus = WorkshopStatus.DRAFT
    seats: List[WorkshopSeat] = Field(default_factory=list)
    session_ids: List[str] = Field(default_factory=list)
    cluster_ref: Optional[str] = None
    target_cluster: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
