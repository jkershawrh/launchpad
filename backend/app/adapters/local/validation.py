from __future__ import annotations

from typing import List

import httpx

from app.domain.enums import ValidationResultStatus
from app.domain.models import LabSession, ValidationResult

GATEWAY_URL = "http://localhost:8080"
FRONTEND_URL = "http://localhost:3030"


class LocalValidationAdapter:
    def validate(self, session: LabSession) -> List[ValidationResult]:
        results = []

        results.append(self._check_endpoint(
            session_id=session.session_id,
            check_name="gateway-health",
            url=f"{GATEWAY_URL}/health",
            expected_status=200,
        ))

        results.append(self._check_endpoint(
            session_id=session.session_id,
            check_name="frontend-reachable",
            url=FRONTEND_URL,
            expected_status=200,
        ))

        results.append(self._check_endpoint(
            session_id=session.session_id,
            check_name="gateway-api-responds",
            url=f"{GATEWAY_URL}/api/v1/requests",
            expected_status=200,
        ))

        return results

    def _check_endpoint(
        self,
        session_id: str,
        check_name: str,
        url: str,
        expected_status: int,
    ) -> ValidationResult:
        try:
            resp = httpx.get(url, timeout=10)
            if resp.status_code == expected_status:
                return ValidationResult(
                    session_id=session_id,
                    check_name=check_name,
                    result=ValidationResultStatus.PASS,
                    message=f"{url} returned {resp.status_code}",
                    evidence=f"HTTP {resp.status_code}",
                )
            else:
                return ValidationResult(
                    session_id=session_id,
                    check_name=check_name,
                    result=ValidationResultStatus.FAIL,
                    message=f"{url} returned {resp.status_code}, expected {expected_status}",
                    evidence=f"HTTP {resp.status_code}",
                )
        except httpx.RequestError as e:
            return ValidationResult(
                session_id=session_id,
                check_name=check_name,
                result=ValidationResultStatus.FAIL,
                message=f"{url} unreachable: {e}",
                evidence=str(e),
            )
