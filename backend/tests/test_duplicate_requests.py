"""Suite 6: Duplicate request handling."""
from app.domain.enums import CatalogCategory
from app.domain.models import LabRequest, Workshop
from app.services.provisioning import ProvisioningService


def _svc(): return ProvisioningService()
def _req(**kw):
    d = dict(tenant_id="dup-t", requester_id="dup-u", catalog_item_id="inference-overdrive-quickstart", requested_mode=CatalogCategory.QUICK_START)
    d.update(kw)
    return LabRequest(**d)


class TestDuplicateRequests:

    def test_same_user_same_catalog_creates_separate_sessions(self):
        svc = _svc()
        r1 = svc.submit_request(_req())
        s1 = svc.provision(r1.request_id)
        r2 = svc.submit_request(_req())
        s2 = svc.provision(r2.request_id)
        assert s1.session_id != s2.session_id

    def test_separate_workshops_for_same_config(self):
        svc = _svc()
        w1 = Workshop(tenant_id="dup-ws", catalog_item_id="inference-overdrive-quickstart", num_users=2, ttl="4h")
        w2 = Workshop(tenant_id="dup-ws", catalog_item_id="inference-overdrive-quickstart", num_users=2, ttl="4h")
        r1 = svc.provision_workshop(w1)
        r2 = svc.provision_workshop(w2)
        assert r1.workshop_id != r2.workshop_id

    def test_different_catalog_items_independent(self):
        svc = _svc()
        r1 = svc.submit_request(_req(catalog_item_id="inference-overdrive-quickstart"))
        s1 = svc.provision(r1.request_id)
        r2 = svc.submit_request(_req(catalog_item_id="build-a-rag-app"))
        s2 = svc.provision(r2.request_id)
        assert s1.catalog_item_id != s2.catalog_item_id
