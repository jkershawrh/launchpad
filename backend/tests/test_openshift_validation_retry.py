from unittest.mock import Mock

from app.adapters.openshift.validation import OpenShiftValidationAdapter
from app.domain.enums import ValidationResultStatus
from app.domain.models import LabSession, ValidationResult


def _result(status: ValidationResultStatus, message: str) -> ValidationResult:
    return ValidationResult(
        session_id="s1", check_name="readiness", result=status, message=message
    )


def _session() -> LabSession:
    return LabSession(request_id="r1", tenant_id="t1", catalog_item_id="c1")


def test_retries_transient_startup_failures_until_ready():
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)
    adapter._sleep = Mock()
    adapter._validation_attempts = 3
    adapter._validation_interval = 0
    adapter._validate_once = Mock(side_effect=[
        [_result(ValidationResultStatus.FAIL, "Pod showroom is in phase Pending")],
        [_result(ValidationResultStatus.FAIL, "Route showroom returned 503")],
        [_result(ValidationResultStatus.PASS, "Route showroom returned 200")],
    ])

    results = adapter.validate(_session())

    assert results[0].result == ValidationResultStatus.PASS
    assert adapter._validate_once.call_count == 3


def test_does_not_retry_non_transient_validation_failure():
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)
    adapter._sleep = Mock()
    adapter._validation_attempts = 3
    adapter._validation_interval = 0
    adapter._validate_once = Mock(return_value=[
        _result(ValidationResultStatus.FAIL, "Pod worker is in phase Failed")
    ])

    results = adapter.validate(_session())

    assert results[0].result == ValidationResultStatus.FAIL
    adapter._validate_once.assert_called_once()
