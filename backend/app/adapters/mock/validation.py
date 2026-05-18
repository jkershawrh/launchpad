from __future__ import annotations

from typing import List

from app.domain.enums import ValidationResultStatus
from app.domain.models import LabSession, ValidationResult


class MockValidationAdapter:
    def validate(self, session: LabSession) -> List[ValidationResult]:
        results = [
            ValidationResult(
                session_id=session.session_id,
                check_name="namespace-exists",
                result=ValidationResultStatus.PASS,
                message=f"Namespace {session.namespace} exists",
                evidence=session.namespace,
            ),
            ValidationResult(
                session_id=session.session_id,
                check_name="lab-url-reachable",
                result=ValidationResultStatus.PASS,
                message=f"Lab URL {session.lab_url} is reachable",
                evidence=session.lab_url,
            ),
            ValidationResult(
                session_id=session.session_id,
                check_name="dashboard-url-reachable",
                result=ValidationResultStatus.PASS,
                message=f"Dashboard URL {session.dashboard_url} is reachable",
                evidence=session.dashboard_url,
            ),
        ]
        return results


class MockFailingValidationAdapter:
    def validate(self, session: LabSession) -> List[ValidationResult]:
        return [
            ValidationResult(
                session_id=session.session_id,
                check_name="namespace-exists",
                result=ValidationResultStatus.PASS,
                message=f"Namespace {session.namespace} exists",
                evidence=session.namespace,
            ),
            ValidationResult(
                session_id=session.session_id,
                check_name="lab-url-reachable",
                result=ValidationResultStatus.FAIL,
                message="Lab URL is unreachable",
                evidence=session.lab_url,
            ),
        ]
