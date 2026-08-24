"""Suite 2: Concurrent session limits."""
import pytest
from app.domain.enums import CatalogCategory
from app.domain.models import LabRequest, Workshop
from app.services.provisioning import ProvisioningService


def _svc(): return ProvisioningService()
def _req(**kw):
    d = dict(tenant_id="limit-t", requester_id="limit-u", catalog_item_id="inference-overdrive-quickstart", requested_mode=CatalogCategory.QUICK_START)
    d.update(kw)
    return LabRequest(**d)
def _provision(svc, **kw):
    r = svc.submit_request(_req(**kw))
    return svc.provision(r.request_id)


class TestSessionLimits:

    def test_user_at_limit_succeeds(self):
        svc = _svc()
        _provision(svc, requester_id="u1")
        s2 = _provision(svc, requester_id="u1")
        assert s2.session_id

    def test_user_over_limit_rejected(self):
        svc = _svc()
        _provision(svc, requester_id="u2")
        _provision(svc, requester_id="u2")
        with pytest.raises(ValueError, match="Session limit"):
            _provision(svc, requester_id="u2")

    def test_tenant_at_limit_succeeds(self):
        svc = _svc()
        for i in range(5):
            _provision(svc, requester_id=f"tu{i}", tenant_id="tenant-lim")

    def test_tenant_over_limit_rejected(self):
        svc = _svc()
        for i in range(5):
            _provision(svc, requester_id=f"tu{i}", tenant_id="tenant-lim2")
        with pytest.raises(ValueError, match="Tenant limit"):
            _provision(svc, requester_id="tu5", tenant_id="tenant-lim2")

    def test_reclaim_frees_slot(self):
        svc = _svc()
        s1 = _provision(svc, requester_id="u3")
        _provision(svc, requester_id="u3")
        svc.force_reclaim_session(s1.session_id)
        s3 = _provision(svc, requester_id="u3")
        assert s3.session_id

    def test_different_users_independent_limits(self):
        svc = _svc()
        _provision(svc, requester_id="ua")
        _provision(svc, requester_id="ua")
        _provision(svc, requester_id="ub")
        _provision(svc, requester_id="ub")

    def test_workshop_bypasses_tenant_limit_uses_workshop_limit(self):
        svc = _svc()
        for i in range(4):
            _provision(svc, requester_id=f"wu{i}", tenant_id="ws-tenant")
        w = Workshop(tenant_id="ws-tenant", catalog_item_id="inference-overdrive-quickstart", num_users=3, ttl="4h")
        result = svc.provision_workshop(w)
        assert len(result.session_ids) == 3
