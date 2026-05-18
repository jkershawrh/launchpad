import pytest
from pydantic import ValidationError

from app.domain.enums import GaudiMode
from app.domain.models import HardwareProfile


def test_hardware_profile_accepts_gaudi_endpoint():
    hp = HardwareProfile(
        hardware_profile_id="gaudi-endpoint",
        display_name="Gaudi Endpoint Access",
        xeon_required=True,
        gaudi_mode=GaudiMode.ENDPOINT,
        openshift_ai_required=True,
    )
    assert hp.gaudi_mode == GaudiMode.ENDPOINT
    assert hp.openshift_ai_required is True


def test_hardware_profile_accepts_gaudi_direct():
    hp = HardwareProfile(
        hardware_profile_id="gaudi-direct",
        display_name="Gaudi Direct Access",
        xeon_required=True,
        gaudi_mode=GaudiMode.DIRECT,
        openshift_ai_required=True,
    )
    assert hp.gaudi_mode == GaudiMode.DIRECT


def test_hardware_profile_defaults():
    hp = HardwareProfile(
        hardware_profile_id="xeon-basic",
        display_name="Xeon Basic",
    )
    assert hp.xeon_required is True
    assert hp.gaudi_mode == GaudiMode.NONE
    assert hp.openshift_ai_required is False
    assert hp.kafka_required is False
    assert hp.virtualization_required is False


def test_hardware_profile_rejects_empty_id():
    with pytest.raises(ValidationError):
        HardwareProfile(
            hardware_profile_id="",
            display_name="Bad",
        )
