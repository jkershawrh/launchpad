from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.adapters.openshift.validation import OpenShiftValidationAdapter
from app.domain.enums import ValidationResultStatus
from app.domain.models import LabSession, ValidationResult


def _result(status: ValidationResultStatus, message: str) -> ValidationResult:
    return ValidationResult(session_id="s1", check_name="readiness", result=status, message=message)


def _session() -> LabSession:
    return LabSession(request_id="r1", tenant_id="t1", catalog_item_id="c1")


def test_retries_transient_startup_failures_until_ready():
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)
    adapter._sleep = Mock()
    adapter._validation_attempts = 3
    adapter._validation_interval = 0
    adapter._validate_once = Mock(
        side_effect=[
            [_result(ValidationResultStatus.FAIL, "Pod showroom is in phase Pending")],
            [_result(ValidationResultStatus.FAIL, "Route showroom returned 503")],
            [_result(ValidationResultStatus.PASS, "Route showroom returned 200")],
        ]
    )

    results = adapter.validate(_session())

    assert results[0].result == ValidationResultStatus.PASS
    assert adapter._validate_once.call_count == 3


def test_does_not_retry_non_transient_validation_failure():
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)
    adapter._sleep = Mock()
    adapter._validation_attempts = 3
    adapter._validation_interval = 0
    adapter._validate_once = Mock(
        return_value=[_result(ValidationResultStatus.FAIL, "Pod worker is in phase Failed")]
    )

    results = adapter.validate(_session())

    assert results[0].result == ValidationResultStatus.FAIL
    adapter._validate_once.assert_called_once()


def test_successfully_completed_pod_is_valid():
    """Finite bootstrap Jobs must not make an otherwise ready lab fail."""
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)
    adapter._core_v1 = Mock()
    adapter._core_v1.list_namespaced_pod.return_value.items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="minio-bootstrap-abc12"),
            status=SimpleNamespace(phase="Succeeded", container_statuses=[]),
        )
    ]

    results = adapter._check_pod_status("s1", "lab-ns")

    assert len(results) == 1
    assert results[0].result == ValidationResultStatus.PASS
    assert "completed successfully" in results[0].message


def test_terminating_failed_rollout_pod_does_not_fail_healthy_replacement():
    """Operators may briefly retain a failed, deleting ReplicaSet pod."""
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)
    adapter._core_v1 = Mock()
    adapter._core_v1.list_namespaced_pod.return_value.items = [
        SimpleNamespace(
            metadata=SimpleNamespace(
                name="ds-pipeline-old", deletion_timestamp="2026-09-06T00:02:00Z"
            ),
            status=SimpleNamespace(phase="Failed", container_statuses=[]),
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="ds-pipeline-current", deletion_timestamp=None),
            status=SimpleNamespace(
                phase="Running",
                container_statuses=[SimpleNamespace(ready=True)],
            ),
        ),
    ]

    results = adapter._check_pod_status("s1", "lab-ns")

    assert [result.check_name for result in results] == ["pod-ds-pipeline-current"]
    assert results[0].result == ValidationResultStatus.PASS


def test_running_unready_pod_is_a_transient_failure():
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)
    adapter._sleep = Mock()
    adapter._validation_attempts = 2
    adapter._validation_interval = 0
    adapter._validate_once = Mock(
        side_effect=[
            [
                _result(
                    ValidationResultStatus.FAIL, "Pod api is running but not all containers ready"
                )
            ],
            [_result(ValidationResultStatus.PASS, "Pod api is running and all containers ready")],
        ]
    )

    results = adapter.validate(_session())

    assert results[0].result == ValidationResultStatus.PASS
    assert adapter._validate_once.call_count == 2


def test_live_validation_window_is_configurable_for_scaled_workshops():
    clients = SimpleNamespace(core=Mock())

    with patch.dict(
        "os.environ",
        {
            "OPENSHIFT_VALIDATION_ATTEMPTS": "61",
            "OPENSHIFT_VALIDATION_INTERVAL_SECONDS": "5",
        },
    ):
        adapter = OpenShiftValidationAdapter(clients=clients)

    assert adapter._validation_attempts == 61
    assert adapter._validation_interval == 5


def test_route_validation_uses_configured_ca_bundle():
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)

    with (
        patch.dict(
            "os.environ",
            {"REQUESTS_CA_BUNDLE": "/etc/launchpad-ca/ca-bundle.crt"},
        ),
        patch("app.adapters.openshift.validation.httpx.get") as request,
    ):
        request.return_value.status_code = 200
        result = adapter._check_route_accessible("s1", "showroom", "https://showroom.example.test")

    assert result.result == ValidationResultStatus.PASS
    request.assert_called_once_with(
        "https://showroom.example.test",
        timeout=10,
        follow_redirects=True,
        verify="/etc/launchpad-ca/ca-bundle.crt",
    )


def test_route_validation_can_explicitly_disable_tls_verification_for_candidate():
    adapter = OpenShiftValidationAdapter.__new__(OpenShiftValidationAdapter)

    with (
        patch.dict(
            "os.environ",
            {
                "OPENSHIFT_ROUTE_TLS_VERIFY": "false",
                "REQUESTS_CA_BUNDLE": "",
                "SSL_CERT_FILE": "",
            },
        ),
        patch("app.adapters.openshift.validation.httpx.get") as request,
    ):
        request.return_value.status_code = 200
        result = adapter._check_route_accessible("s1", "demo", "https://demo.example.test")

    assert result.result == ValidationResultStatus.PASS
    request.assert_called_once_with(
        "https://demo.example.test",
        timeout=10,
        follow_redirects=True,
        verify=False,
    )
