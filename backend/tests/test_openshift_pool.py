"""Tests for direct OpenShift capacity and reservation handling."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.adapters.openshift.pool import OpenShiftPoolAdapter


def _adapter(allowed=True):
    adapter = OpenShiftPoolAdapter.__new__(OpenShiftPoolAdapter)
    adapter._authorization = MagicMock()
    adapter._authorization.create_self_subject_access_review.return_value = SimpleNamespace(
        status=SimpleNamespace(allowed=allowed)
    )
    adapter._reservations = {}
    import threading

    adapter._lock = threading.Lock()
    return adapter


def test_capacity_reflects_namespace_create_authorization():
    assert _adapter(allowed=True).check_capacity("xeon-basic", "small") is True
    assert _adapter(allowed=False).check_capacity("xeon-basic", "small") is False


def test_reserve_report_and_release():
    adapter = _adapter()

    reservation = adapter.reserve("request-1", "xeon-basic", "small")

    assert reservation["provider"] == "openshift"
    assert adapter.report_allocation()["total_reservations"] == 1
    assert adapter.release("request-1") is True
    assert adapter.release("request-1") is False
    assert adapter.report_allocation()["total_reservations"] == 0
