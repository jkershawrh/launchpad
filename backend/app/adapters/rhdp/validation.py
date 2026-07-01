from __future__ import annotations

import logging
from typing import List

from app.domain.enums import ValidationResultStatus
from app.domain.models import LabSession, ValidationResult

logger = logging.getLogger(__name__)


class RHDPValidationAdapter:
    """Validates sessions provisioned via the RHDP Sandbox API.

    Scope: checks that Sandbox API returned a placement, namespace, and lab URL.
    Deeper validation (pod readiness, route accessibility, workload health) is
    StarGate's responsibility via rubric evaluation and event-driven monitoring.
    """

    def validate(self, session: LabSession) -> List[ValidationResult]:
        results = []

        results.append(ValidationResult(
            session_id=session.session_id,
            check_name="sandbox-placement",
            result=ValidationResultStatus.PASS
            if session.resources.get("sandbox_name")
            else ValidationResultStatus.FAIL,
            message="Sandbox placement exists" if session.resources.get("sandbox_name")
            else "No sandbox placement found",
        ))

        results.append(ValidationResult(
            session_id=session.session_id,
            check_name="namespace-exists",
            result=ValidationResultStatus.PASS
            if session.namespace
            else ValidationResultStatus.FAIL,
            message=f"Namespace: {session.namespace}" if session.namespace
            else "No namespace assigned",
        ))

        if session.lab_url:
            results.append(ValidationResult(
                session_id=session.session_id,
                check_name="lab-url-set",
                result=ValidationResultStatus.PASS,
                message=f"Lab URL: {session.lab_url}",
            ))

        return results
