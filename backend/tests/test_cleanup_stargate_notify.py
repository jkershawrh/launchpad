"""TDD: notify_stargate must be called on CLEANUP_FAILED."""
from unittest.mock import patch, MagicMock
from app.domain.enums import CatalogCategory
from app.domain.models import LabRequest
from app.services.provisioning import ProvisioningService


def _svc(**kw):
    return ProvisioningService(**kw)

def _req(**kw):
    d = dict(tenant_id="notify-t", requester_id="notify-u", catalog_item_id="inference-overdrive-quickstart", requested_mode=CatalogCategory.QUICK_START)
    d.update(kw)
    return LabRequest(**d)


class TestCleanupStarGateNotify:

    def test_cleanup_failure_posts_to_stargate(self):
        """RED: when cleanup fails, notify_stargate should be called with status=cleanup_failed."""
        mock_cleanup = MagicMock()
        mock_cleanup.cleanup.side_effect = Exception("namespace stuck")
        svc = _svc(cleanup=mock_cleanup)
        r = svc.submit_request(_req())
        session = svc.provision(r.request_id)
        validated = svc.validate_session(session.session_id)
        activated = svc.activate_session(validated.session_id)
        reset = svc.reset_session(activated.session_id)

        with patch("app.services.provisioning.notify_stargate") as mock_notify:
            try:
                svc.reclaim_session(reset.session_id)
            except Exception:
                pass
            cleanup_calls = [c for c in mock_notify.call_args_list if "cleanup_failed" in str(c)]
            assert len(cleanup_calls) > 0, f"notify_stargate not called with cleanup_failed. Calls: {mock_notify.call_args_list}"

    def test_successful_cleanup_posts_reclaimed(self):
        """GREEN baseline: successful cleanup should post reclaimed, not cleanup_failed."""
        svc = _svc()
        r = svc.submit_request(_req())
        session = svc.provision(r.request_id)
        validated = svc.validate_session(session.session_id)
        activated = svc.activate_session(validated.session_id)
        reset = svc.reset_session(activated.session_id)

        with patch("app.services.provisioning.notify_stargate") as mock_notify:
            svc.reclaim_session(reset.session_id)
            reclaim_calls = [c for c in mock_notify.call_args_list if "reclaimed" in str(c)]
            assert len(reclaim_calls) > 0
