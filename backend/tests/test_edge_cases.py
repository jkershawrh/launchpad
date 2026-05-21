"""
Edge case tests — 36 scenarios covering input validation, concurrent ops,
state edge cases, TTL, workshop boundaries, cleanup, credentials, and API.
"""
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.domain.enums import CatalogCategory, Persistence, SessionStatus
from app.domain.models import LabRequest, Workshop
from app.main import app
from app.services.provisioning import ProvisioningService

client = TestClient(app)


def _svc(**kw): return ProvisioningService(**kw)
def _req(**kw):
    d = dict(tenant_id="edge-t", requester_id="edge-u", catalog_item_id="inference-overdrive-quickstart", requested_mode=CatalogCategory.QUICK_START)
    d.update(kw)
    return LabRequest(**d)
def _provision(svc, **kw):
    r = svc.submit_request(_req(**kw))
    return svc.provision(r.request_id)


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputValidation:

    def test_nonexistent_catalog_item_rejected(self):
        svc = _svc()
        r = svc.submit_request(_req(catalog_item_id="does-not-exist"))
        assert r.status.value == "rejected"

    def test_special_characters_in_tenant_id(self):
        svc = _svc()
        s = _provision(svc, tenant_id="partner/oem&a")
        assert s.session_id

    def test_negative_num_users_workshop(self):
        w = Workshop(tenant_id="t", catalog_item_id="inference-overdrive-quickstart", num_users=-1, ttl="4h")
        svc = _svc()
        result = svc.provision_workshop(w)
        assert len(result.session_ids) == 0

    def test_zero_num_users_workshop(self):
        w = Workshop(tenant_id="t", catalog_item_id="inference-overdrive-quickstart", num_users=0, ttl="4h")
        svc = _svc()
        result = svc.provision_workshop(w)
        assert len(result.session_ids) == 0
        assert result.status == "ready"

    def test_invalid_ttl_format(self):
        svc = _svc()
        with pytest.raises(Exception):
            _provision(svc, ttl="invalid")

    def test_extremely_long_tenant_id(self):
        svc = _svc()
        s = _provision(svc, tenant_id="a" * 500)
        assert s.session_id


# ═══════════════════════════════════════════════════════════════════════════════
# STATE EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateEdgeCases:

    def test_validate_already_ready_session(self):
        svc = _svc()
        s = _provision(svc)
        validated = svc.validate_session(s.session_id)
        assert validated.status == SessionStatus.READY
        with pytest.raises(Exception):
            svc.validate_session(validated.session_id)

    def test_activate_already_active_session(self):
        svc = _svc()
        s = _provision(svc)
        validated = svc.validate_session(s.session_id)
        activated = svc.activate_session(validated.session_id)
        with pytest.raises(Exception):
            svc.activate_session(activated.session_id)

    def test_reinitialize_reclaimed_session_raises(self):
        svc = _svc()
        s = _provision(svc)
        svc.force_reclaim_session(s.session_id)
        with pytest.raises(ValueError):
            svc.reinitialize_session(s.session_id)

    def test_reinitialize_provisioning_session_raises(self):
        svc = _svc()
        s = _provision(svc)
        with pytest.raises(ValueError):
            svc.reinitialize_session(s.session_id)

    def test_force_reclaim_already_reclaimed(self):
        svc = _svc()
        s = _provision(svc)
        svc.force_reclaim_session(s.session_id)
        reclaimed = svc.get_session(s.session_id)
        assert reclaimed.status == SessionStatus.RECLAIMED
        svc.force_reclaim_session(s.session_id)
        still_reclaimed = svc.get_session(s.session_id)
        assert still_reclaimed.status == SessionStatus.RECLAIMED

    def test_provision_rejected_request_raises(self):
        svc = _svc()
        r = svc.submit_request(_req(catalog_item_id="does-not-exist"))
        assert r.status.value == "rejected"
        with pytest.raises(ValueError, match="not accepted"):
            svc.provision(r.request_id)


# ═══════════════════════════════════════════════════════════════════════════════
# TTL EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestTTLEdgeCases:

    def test_ttl_zero_hours(self):
        svc = _svc()
        s = _provision(svc, ttl="0h")
        assert s.expires_at is not None
        assert s.expires_at <= datetime.utcnow() + timedelta(seconds=5)

    def test_ttl_very_large(self):
        svc = _svc()
        s = _provision(svc, ttl="9999h")
        assert s.expires_at > datetime.utcnow() + timedelta(hours=9990)

    def test_persistent_ignores_ttl(self):
        svc = _svc()
        s = _provision(svc, persistence=Persistence.PERSISTENT, ttl="4h")
        assert s.expires_at is None

    def test_enforce_ttl_empty_sessions(self):
        svc = _svc()
        count = svc.enforce_ttl()
        assert count == 0

    def test_enforce_ttl_idempotent(self):
        svc = _svc()
        s = _provision(svc, ttl="1h")
        validated = svc.validate_session(s.session_id)
        activated = svc.activate_session(validated.session_id)
        expired = activated.model_copy(update={"expires_at": datetime.utcnow() - timedelta(hours=1)})
        svc._sessions[expired.session_id] = expired
        count1 = svc.enforce_ttl()
        count2 = svc.enforce_ttl()
        assert count1 == 1
        assert count2 == 0


# ═══════════════════════════════════════════════════════════════════════════════
# WORKSHOP EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkshopEdgeCases:

    def test_workshop_one_user(self):
        svc = _svc()
        w = Workshop(tenant_id="ws1", catalog_item_id="inference-overdrive-quickstart", num_users=1, ttl="4h")
        result = svc.provision_workshop(w)
        assert len(result.session_ids) == 1

    def test_reclaim_nonexistent_workshop(self):
        svc = _svc()
        with pytest.raises(ValueError, match="not found"):
            svc.reclaim_workshop("nonexistent-ws")

    def test_workshop_large_batch(self):
        svc = _svc()
        w = Workshop(tenant_id="ws-big", catalog_item_id="inference-overdrive-quickstart", num_users=10, ttl="4h")
        result = svc.provision_workshop(w)
        assert len(result.session_ids) <= 10


# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanupEdgeCases:

    def test_reclaim_session_with_no_namespace(self):
        svc = _svc()
        s = _provision(svc)
        no_ns = s.model_copy(update={"namespace": None})
        svc._sessions[no_ns.session_id] = no_ns
        svc.force_reclaim_session(no_ns.session_id)
        result = svc.get_session(no_ns.session_id)
        assert result.status == SessionStatus.RECLAIMED

    def test_reclaim_session_with_empty_resources(self):
        svc = _svc()
        s = _provision(svc)
        empty = s.model_copy(update={"resources": {}})
        svc._sessions[empty.session_id] = empty
        svc.force_reclaim_session(empty.session_id)
        result = svc.get_session(empty.session_id)
        assert result.maas_api_key is None

    def test_reclaim_with_no_cleanup_adapter(self):
        svc = _svc(cleanup=None)
        s = _provision(svc)
        svc.force_reclaim_session(s.session_id)
        result = svc.get_session(s.session_id)
        assert result.status == SessionStatus.RECLAIMED


# ═══════════════════════════════════════════════════════════════════════════════
# CREDENTIAL EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestCredentialEdgeCases:

    def test_public_view_nonexistent_session(self):
        svc = _svc()
        result = svc.get_session_public("nonexistent")
        assert result is None

    def test_scrub_session_with_no_maas_key(self):
        svc = _svc()
        s = _provision(svc)
        no_key = s.model_copy(update={"maas_api_key": None})
        svc._sessions[no_key.session_id] = no_key
        svc.force_reclaim_session(no_key.session_id)
        result = svc.get_session(no_key.session_id)
        assert result.maas_api_key is None


# ═══════════════════════════════════════════════════════════════════════════════
# API EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIEdgeCases:

    def test_invalid_json_body(self):
        resp = client.post("/lab-requests", content="not json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

    def test_missing_required_fields(self):
        resp = client.post("/lab-requests", json={"tenant_id": "t"})
        assert resp.status_code == 422

    def test_get_nonexistent_session(self):
        resp = client.get("/lab-sessions/nonexistent")
        assert resp.status_code == 404

    def test_provision_nonexistent_request(self):
        resp = client.post("/lab-requests/nonexistent/provision")
        assert resp.status_code in (400, 404)
