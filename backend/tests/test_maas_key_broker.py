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
    broker.create_key.return_value.key_id = "token-seat-1"
    service = ProvisioningService(maas_key_broker=broker)
    request = service.submit_request(_request())

    session = service.provision(request.request_id)
    assert session.maas_api_key == "sk-gateway-issued"
    issue = broker.create_key.call_args.kwargs
    assert issue["duration"] == "4h"
    assert issue["alias"] == f"launchpad-{session.session_id}"
    assert issue["metadata"]["session_id"] == session.session_id
    assert issue["metadata"]["request_id"] == request.request_id
    assert issue["metadata"]["catalog_item_id"] == request.catalog_item_id
    assert session.metadata["maas_key_id"] == "token-seat-1"
    assert session.metadata["maas_key_alias"] == f"launchpad-{session.session_id}"
    assert session.metadata["inference_attribution"] == "litellm_virtual_key"
    assert "sk-gateway-issued" not in session.metadata.values()

    reclaimed = service.force_reclaim_session(session.session_id)
    broker.revoke_key.assert_called_once_with("sk-gateway-issued")
    assert reclaimed.maas_api_key is None
    assert reclaimed.metadata["maas_key_id"] == "token-seat-1"


def test_virtual_key_metadata_carries_workshop_and_seat_identity():
    broker = MagicMock()
    broker.create_key.return_value.key = "sk-workshop-seat"
    broker.create_key.return_value.key_id = "token-workshop-seat"
    service = ProvisioningService(maas_key_broker=broker)
    request = service.submit_request(
        LabRequest(
            tenant_id="tenant-a",
            requester_id="participant-7",
            catalog_item_id="inference-overdrive-quickstart",
            requested_mode=CatalogCategory.QUICK_START,
            ttl="4h",
            metadata={
                "workshop_id": "workshop-1",
                "seat_id": "seat-7",
                "seat_number": 7,
            },
        )
    )

    session = service.provision(request.request_id)
    metadata = broker.create_key.call_args.kwargs["metadata"]

    assert metadata["session_id"] == session.session_id
    assert metadata["workshop_id"] == "workshop-1"
    assert metadata["seat_id"] == "seat-7"
    assert metadata["seat_number"] == 7


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


def test_direct_model_endpoint_is_explicitly_not_reported_as_key_attributed():
    service = ProvisioningService()
    request = service.submit_request(_request())

    session = service.provision(request.request_id)

    assert session.metadata["inference_attribution"] == (
        "direct_endpoint_unattributed"
    )
    assert "maas_key_id" not in session.metadata
    assert "maas_key_alias" not in session.metadata
