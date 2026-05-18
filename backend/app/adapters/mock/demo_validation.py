from __future__ import annotations

from typing import List

from app.domain.enums import ValidationResultStatus
from app.domain.models import LabSession, ValidationResult


class DemoValidationAdapter:
    def validate(self, session: LabSession) -> List[ValidationResult]:
        results = [
            ValidationResult(
                session_id=session.session_id,
                check_name="gateway-health",
                result=ValidationResultStatus.PASS,
                message="Gateway module is healthy",
                evidence="gateway module found",
            ),
            ValidationResult(
                session_id=session.session_id,
                check_name="demo-source-exists",
                result=ValidationResultStatus.PASS,
                message="Demo source path exists in demos/",
                evidence=f"namespace={session.namespace}",
            ),
            ValidationResult(
                session_id=session.session_id,
                check_name="config-valid",
                result=ValidationResultStatus.PASS,
                message="Demo has required configuration",
                evidence="config validated",
            ),
        ]
        return results


class DemoFailingValidationAdapter:
    def validate(self, session: LabSession) -> List[ValidationResult]:
        return [
            ValidationResult(
                session_id=session.session_id,
                check_name="gateway-health",
                result=ValidationResultStatus.FAIL,
                message="Gateway module is unreachable",
                evidence="connection refused",
            ),
            ValidationResult(
                session_id=session.session_id,
                check_name="demo-source-exists",
                result=ValidationResultStatus.FAIL,
                message="Demo source path not found in demos/",
                evidence="path missing",
            ),
            ValidationResult(
                session_id=session.session_id,
                check_name="config-valid",
                result=ValidationResultStatus.FAIL,
                message="Demo configuration is invalid",
                evidence="missing required fields",
            ),
        ]
