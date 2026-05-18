import pytest
from pydantic import ValidationError

from app.domain.models import QuotaProfile


def test_quota_profile_validates_limits():
    qp = QuotaProfile(
        quota_profile_id="standard",
        cpu_limit="8",
        memory_limit="16Gi",
        storage_limit="50Gi",
        max_pods=30,
        max_routes=10,
        ttl_max="12h",
    )
    assert qp.max_pods == 30
    assert qp.max_routes == 10
    assert qp.cpu_limit == "8"
    assert qp.gaudi_access_limit is None


def test_quota_profile_rejects_zero_pods():
    with pytest.raises(ValidationError):
        QuotaProfile(
            quota_profile_id="bad",
            cpu_limit="1",
            memory_limit="1Gi",
            storage_limit="1Gi",
            max_pods=0,
            max_routes=1,
        )


def test_quota_profile_rejects_negative_routes():
    with pytest.raises(ValidationError):
        QuotaProfile(
            quota_profile_id="bad",
            cpu_limit="1",
            memory_limit="1Gi",
            storage_limit="1Gi",
            max_pods=1,
            max_routes=-1,
        )


def test_quota_profile_with_gaudi_limit():
    qp = QuotaProfile(
        quota_profile_id="large",
        cpu_limit="32",
        memory_limit="64Gi",
        storage_limit="200Gi",
        max_pods=100,
        max_routes=25,
        gaudi_access_limit=2,
    )
    assert qp.gaudi_access_limit == 2
