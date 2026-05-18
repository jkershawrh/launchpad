import pytest
from pydantic import ValidationError

from app.domain.enums import TenantStatus, TenantType
from app.domain.models import Tenant


def test_tenant_model_accepts_valid_partner(valid_tenant):
    assert valid_tenant.tenant_id == "partner-oem-a"
    assert valid_tenant.tenant_type == TenantType.PARTNER
    assert valid_tenant.status == TenantStatus.ACTIVE
    assert valid_tenant.branding_profile_id == "partner-oem-a"
    assert valid_tenant.default_quota_profile == "standard"
    assert valid_tenant.default_ttl == "8h"
    assert valid_tenant.cost_center == "demo-partner-oem-a"


def test_tenant_model_rejects_missing_id():
    with pytest.raises(ValidationError):
        Tenant(
            tenant_id="",
            display_name="Bad Tenant",
            tenant_type=TenantType.PARTNER,
        )


def test_tenant_model_rejects_missing_display_name():
    with pytest.raises(ValidationError):
        Tenant(
            tenant_id="valid-id",
            display_name="  ",
            tenant_type=TenantType.PARTNER,
        )


def test_tenant_accepts_all_types():
    for tt in TenantType:
        t = Tenant(tenant_id=f"test-{tt.value}", display_name="Test", tenant_type=tt)
        assert t.tenant_type == tt
