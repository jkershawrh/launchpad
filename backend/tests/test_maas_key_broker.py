from unittest.mock import MagicMock, patch

import pytest

from app.adapters.openshift.maas_keys import LiteLLMVirtualKeyBroker
from app.domain.enums import CatalogCategory
from app.domain.models import LabRequest
from app.services.provisioning import ProvisioningService


def test_virtual_key_is_scoped_and_limited():
    response = MagicMock()
    response.json.return_value = {"key": "sk-real", "token_id": "token-1"}
    with patch("httpx.post", return_value=response) as post:
        broker = LiteLLMVirtualKeyBroker("http://litellm:4000", "master")
        result = broker.create_key(
            alias="lab-session-1", duration="4h", models=["granite"],
            rpm_limit=60, metadata={"session_id": "session-1"},
        )

    assert result.key == "sk-real"
    assert result.key_id == "token-1"
    request = post.call_args
    assert request.args[0] == "http://litellm:4000/key/generate"
    assert request.kwargs["headers"] == {"Authorization": "Bearer master"}
    assert request.kwargs["json"]["models"] == ["granite"]
    assert request.kwargs["json"]["rpm_limit"] == 60
    response.raise_for_status.assert_called_once()


def test_virtual_key_generation_fails_without_returned_key():
    response = MagicMock()
    response.json.return_value = {"token_id": "token-1"}
    with patch("httpx.post", return_value=response):
        broker = LiteLLMVirtualKeyBroker("http://litellm:4000", "master")
        with pytest.raises(ValueError, match="returned no key"):
            broker.create_key(
                alias="lab", duration="1h", models=[], rpm_limit=10, metadata={},
            )


def test_virtual_key_is_revoked_at_gateway():
    response = MagicMock()
    with patch("httpx.post", return_value=response) as post:
        broker = LiteLLMVirtualKeyBroker("http://litellm:4000", "master")
        broker.revoke_key("sk-real")

    assert post.call_args.args[0] == "http://litellm:4000/key/delete"
    assert post.call_args.kwargs["json"] == {"keys": ["sk-real"]}
    response.raise_for_status.assert_called_once()


def _request():
    return LabRequest(
        tenant_id="tenant-a", requester_id="user-a",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START, ttl="4h",
    )


def test_provisioning_uses_broker_key_and_reclaim_revokes_it():
    broker = MagicMock()
    broker.create_key.return_value.key = "sk-gateway-issued"
    service = ProvisioningService(maas_key_broker=broker)
    request = service.submit_request(_request())

    session = service.provision(request.request_id)
    assert session.maas_api_key == "sk-gateway-issued"
    assert broker.create_key.call_args.kwargs["duration"] == "4h"

    reclaimed = service.force_reclaim_session(session.session_id)
    broker.revoke_key.assert_called_once_with("sk-gateway-issued")
    assert reclaimed.maas_api_key is None


def test_provisioning_fails_closed_and_releases_reservation_on_key_error():
    broker = MagicMock()
    broker.create_key.side_effect = RuntimeError("gateway unavailable")
    pool = MagicMock()
    pool.check_capacity.return_value = True
    pool.reserve.return_value = {}
    service = ProvisioningService(maas_key_broker=broker, pool=pool)
    request = service.submit_request(_request())

    with pytest.raises(ValueError, match="Failed to issue MaaS access key"):
        service.provision(request.request_id)

    pool.release.assert_called_once_with(request.request_id)
