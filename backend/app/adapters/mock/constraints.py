from __future__ import annotations

from app.domain.models import LabRequest
from app.adapters.interfaces import ConstraintResult


class MockConstraintAdapter:
    def evaluate(self, request: LabRequest) -> ConstraintResult:
        if not request.tenant_id or not request.catalog_item_id:
            return ConstraintResult(
                allowed=False,
                level="blocked",
                reasons=["Missing required fields"],
            )
        return ConstraintResult(allowed=True, level="allowed")


class FailingConstraintAdapter:
    def evaluate(self, request: LabRequest) -> ConstraintResult:
        return ConstraintResult(
            allowed=False,
            level="blocked",
            reasons=["Tenant not authorized for this catalog item"],
        )
