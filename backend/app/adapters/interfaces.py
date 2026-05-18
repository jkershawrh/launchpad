from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from app.domain.enums import ValidationResultStatus
from app.domain.models import (
    BrandingProfile,
    CatalogItem,
    LabRequest,
    LabSession,
    ProvisioningPlan,
    ShowbackRecord,
    ValidationResult,
)
from app.domain.reports import SecurityPlan


class CatalogAdapter(Protocol):
    def list_items(self) -> List[CatalogItem]: ...
    def get_item(self, catalog_item_id: str) -> Optional[CatalogItem]: ...
    def validate_item(self, catalog_item_id: str) -> bool: ...


class PoolAdapter(Protocol):
    def check_capacity(self, hardware_profile: str, quota_profile: str) -> bool: ...
    def reserve(self, session_id: str, hardware_profile: str, quota_profile: str) -> Dict[str, Any]: ...
    def release(self, session_id: str) -> bool: ...
    def report_allocation(self) -> Dict[str, Any]: ...


class ConstraintAdapter(Protocol):
    def evaluate(self, request: LabRequest) -> ConstraintResult: ...


class ConstraintResult:
    def __init__(self, allowed: bool, level: str = "allowed", reasons: Optional[List[str]] = None):
        self.allowed = allowed
        self.level = level  # allowed | warn | blocked
        self.reasons = reasons or []


class ProvisioningAdapter(Protocol):
    def create_plan(self, request: LabRequest, catalog_item: CatalogItem) -> ProvisioningPlan: ...
    def provision(self, plan: ProvisioningPlan) -> ProvisionResult: ...


class ProvisionResult:
    def __init__(
        self,
        namespace: str,
        lab_url: str,
        dashboard_url: str,
        resources: Optional[Dict[str, Any]] = None,
    ):
        self.namespace = namespace
        self.lab_url = lab_url
        self.dashboard_url = dashboard_url
        self.resources = resources or {}


class ValidationAdapter(Protocol):
    def validate(self, session: LabSession) -> List[ValidationResult]: ...


class ObservabilityAdapter(Protocol):
    def create_dashboard(self, session: LabSession) -> str: ...
    def get_metrics(self, session_id: str) -> Dict[str, Any]: ...
    def get_health(self, session_id: str) -> str: ...


class ShowbackAdapter(Protocol):
    def create_record(self, session: LabSession) -> ShowbackRecord: ...
    def summarize(self, tenant_id: str) -> Dict[str, Any]: ...
    def export_report(self, session_id: str, fmt: str = "json") -> str: ...


class BrandingAdapter(Protocol):
    def load_profile(self, branding_profile_id: str) -> Optional[BrandingProfile]: ...
    def list_profiles(self) -> List[BrandingProfile]: ...


class AutomationGenerator(Protocol):
    def generate(self, request: LabRequest, catalog_item: CatalogItem) -> AutomationBundle: ...


class AutomationBundle:
    def __init__(
        self,
        artifacts: Optional[Dict[str, str]] = None,
        validated: bool = False,
        dry_run_passed: bool = False,
    ):
        self.artifacts = artifacts or {}
        self.validated = validated
        self.dry_run_passed = dry_run_passed
