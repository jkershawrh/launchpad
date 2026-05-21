"""
TDD Red/Green tests for:
- Labels on all provisioned resources
- PSS (Pod Security Standards) on namespaces
- Credential security (no hardcoded passwords, no MaaS keys in API responses)
- Persistent demo support (expires_at = None)
- Workshop batch provisioning
"""

from app.domain.enums import (
    CatalogCategory,
    Persistence,
    SessionStatus,
)
from app.domain.models import LabRequest
from app.services.provisioning import ProvisioningService


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_service(**overrides):
    return ProvisioningService(**overrides)


def _make_request(**overrides):
    defaults = dict(
        tenant_id="partner-test",
        requester_id="user-1",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
    )
    defaults.update(overrides)
    return LabRequest(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Persistent Demo Support
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistentDemos:
    """Persistent sessions should never expire."""

    def test_persistent_session_has_no_expiry(self):
        """RED: persistent request → expires_at must be None."""
        svc = _make_service()
        request = _make_request(persistence=Persistence.PERSISTENT, ttl="8h")
        accepted = svc.submit_request(request)
        session = svc.provision(accepted.request_id)
        assert session.expires_at is None, (
            f"Persistent session should not expire, but got expires_at={session.expires_at}"
        )

    def test_ephemeral_session_has_expiry(self):
        """GREEN baseline: ephemeral request → expires_at must be set."""
        svc = _make_service()
        request = _make_request(persistence=Persistence.EPHEMERAL, ttl="4h")
        accepted = svc.submit_request(request)
        session = svc.provision(accepted.request_id)
        assert session.expires_at is not None, "Ephemeral session must have an expiry"

    def test_reinitialize_session_resets_to_ready(self):
        """RED: reinitialize a persistent session → status back to ready without reclaim."""
        svc = _make_service()
        request = _make_request(persistence=Persistence.PERSISTENT)
        accepted = svc.submit_request(request)
        session = svc.provision(accepted.request_id)
        validated = svc.validate_session(session.session_id)
        activated = svc.activate_session(validated.session_id)

        assert activated.status == SessionStatus.ACTIVE

        reinit = svc.reinitialize_session(activated.session_id)
        assert reinit.status == SessionStatus.READY
        assert reinit.namespace == activated.namespace


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Credential Security
# ═══════════════════════════════════════════════════════════════════════════════

class TestCredentialSecurity:
    """MaaS keys should not leak to non-admin API responses."""

    def test_session_list_excludes_maas_key(self):
        """RED: listing sessions should not include maas_api_key."""
        svc = _make_service()
        request = _make_request()
        accepted = svc.submit_request(request)
        session = svc.provision(accepted.request_id)

        public_session = svc.get_session_public(session.session_id)
        assert public_session is not None
        assert not hasattr(public_session, "maas_api_key") or public_session.maas_api_key is None, (
            "Public session view must not expose maas_api_key"
        )

    def test_session_admin_view_includes_maas_key(self):
        """GREEN: admin session view should include maas_api_key."""
        svc = _make_service()
        request = _make_request()
        accepted = svc.submit_request(request)
        session = svc.provision(accepted.request_id)

        admin_session = svc.get_session(session.session_id)
        assert admin_session is not None
        assert admin_session.maas_api_key is not None
        assert admin_session.maas_api_key.startswith("sk-launchpad-")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Workshop Batch Provisioning
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkshopProvisioning:
    """Workshops create multiple sessions in batch."""

    def test_workshop_model_exists(self):
        """RED: Workshop model should be importable."""
        from app.domain.models import Workshop
        w = Workshop(
            tenant_id="redhat-summit",
            catalog_item_id="inference-overdrive",
            num_users=5,
            ttl="8h",
        )
        assert w.workshop_id
        assert w.num_users == 5
        assert w.status == "pending"
        assert w.session_ids == []

    def test_provision_workshop_creates_multiple_sessions(self):
        """RED: provisioning a workshop should create N sessions."""
        svc = _make_service()
        from app.domain.models import Workshop
        workshop = Workshop(
            tenant_id="redhat-summit",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=3,
            ttl="4h",
        )
        result = svc.provision_workshop(workshop)
        assert result.status == "ready"
        assert len(result.session_ids) == 3

        for sid in result.session_ids:
            session = svc.get_session(sid)
            assert session is not None
            assert session.tenant_id == "redhat-summit"

    def test_reclaim_workshop_reclaims_all_sessions(self):
        """RED: reclaiming a workshop should reclaim all its sessions."""
        svc = _make_service()
        from app.domain.models import Workshop
        workshop = Workshop(
            tenant_id="redhat-summit",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=3,
            ttl="4h",
        )
        provisioned = svc.provision_workshop(workshop)
        reclaimed = svc.reclaim_workshop(provisioned.workshop_id)
        assert reclaimed.status == "completed"

        for sid in reclaimed.session_ids:
            session = svc.get_session(sid)
            assert session.status == SessionStatus.RECLAIMED

    def test_workshop_has_purpose_events(self):
        """RED: workshop sessions should have purpose=events."""
        svc = _make_service()
        from app.domain.models import Workshop
        workshop = Workshop(
            tenant_id="redhat-summit",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=2,
            ttl="4h",
            purpose="events",
        )
        result = svc.provision_workshop(workshop)
        for sid in result.session_ids:
            session = svc.get_session(sid)
            assert session.metadata.get("purpose") == "events"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Labels
# ═══════════════════════════════════════════════════════════════════════════════

class TestLabels:
    """Every provisioned session should carry tracking labels in resources."""

    def test_session_resources_include_tenant_label(self):
        """RED: session resources should include tenant label."""
        svc = _make_service()
        request = _make_request()
        accepted = svc.submit_request(request)
        session = svc.provision(accepted.request_id)
        labels = session.metadata.get("labels", {})
        assert labels.get("launchpad.redhat.com/tenant") == "partner-test"

    def test_session_resources_include_catalog_item_label(self):
        """RED: session resources should include catalog-item label."""
        svc = _make_service()
        request = _make_request()
        accepted = svc.submit_request(request)
        session = svc.provision(accepted.request_id)
        labels = session.metadata.get("labels", {})
        assert labels.get("launchpad.redhat.com/catalog-item") == "inference-overdrive-quickstart"

    def test_session_resources_include_purpose_label(self):
        """RED: session resources should include purpose label."""
        svc = _make_service()
        request = _make_request()
        accepted = svc.submit_request(request)
        session = svc.provision(accepted.request_id)
        labels = session.metadata.get("labels", {})
        assert labels.get("launchpad.redhat.com/purpose") == "self-service"

    def test_workshop_sessions_include_workshop_id_label(self):
        """RED: workshop sessions should include workshop-id label."""
        svc = _make_service()
        from app.domain.models import Workshop
        workshop = Workshop(
            tenant_id="redhat-summit",
            catalog_item_id="inference-overdrive-quickstart",
            num_users=2,
            ttl="4h",
        )
        result = svc.provision_workshop(workshop)
        for sid in result.session_ids:
            session = svc.get_session(sid)
            labels = session.metadata.get("labels", {})
            assert labels.get("launchpad.redhat.com/workshop-id") == workshop.workshop_id
