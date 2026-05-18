from app.domain.enums import SessionStatus
from app.domain.models import LabSession


def test_lab_session_defaults(lab_session):
    assert lab_session.status == SessionStatus.REQUESTED
    assert lab_session.namespace == "lab-partner-oem-a-001"
    assert lab_session.lab_url is None
    assert lab_session.validation_results == []
    assert lab_session.lifecycle_events == []
    assert lab_session.session_id  # auto-generated


def test_lab_session_auto_generates_session_id():
    s = LabSession(
        request_id="r1",
        tenant_id="t1",
        catalog_item_id="c1",
    )
    assert len(s.session_id) == 36
