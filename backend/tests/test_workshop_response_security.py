"""Requester, participant, and operator workshop views must not expose secrets."""

from unittest.mock import patch

import pytest
from app.api.deps import provisioning_service
from app.auth.oauth import User, get_current_user
from app.domain.models import Workshop, WorkshopSeat
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_state():
    provisioning_service._workshops.clear()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def workshop() -> Workshop:
    workshop = Workshop(
        tenant_id="partner-a",
        catalog_item_id="catalog-1",
        num_users=1,
        seats=[
            WorkshopSeat(
                workshop_id="workshop-1",
                seat_number=1,
                metadata={
                    "workspace_password": "seat-password-secret",
                    "nested": {"api_key": "seat-api-secret", "note": "safe-seat"},
                },
            )
        ],
        metadata={
            "credential_secret": "workshop-credential-secret",
            "nested": {"refresh_token": "workshop-refresh-secret", "note": "safe-order"},
        },
    )
    workshop.seats[0].workshop_id = workshop.workshop_id
    provisioning_service._workshops[workshop.workshop_id] = workshop
    return workshop


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: User(
        username="partner-user", tenant_ids=["partner-a"]
    )
    return TestClient(app)


def _assert_secret_free(payload: dict) -> None:
    rendered = str(payload)
    for secret in (
        "seat-password-secret",
        "seat-api-secret",
        "workshop-credential-secret",
        "workshop-refresh-secret",
    ):
        assert secret not in rendered
    assert payload["metadata"] == {"nested": {"note": "safe-order"}}
    assert payload["seats"][0]["metadata"] == {"nested": {"note": "safe-seat"}}


def test_workshop_list_and_detail_redact_nested_metadata(
    client: TestClient, workshop: Workshop
) -> None:
    listed = client.get("/api/v1/workshops")
    detailed = client.get(f"/api/v1/workshops/{workshop.workshop_id}")

    assert listed.status_code == 200
    assert detailed.status_code == 200
    _assert_secret_free(listed.json()[0])
    _assert_secret_free(detailed.json())
    assert workshop.metadata["credential_secret"] == "workshop-credential-secret"
    assert workshop.seats[0].metadata["workspace_password"] == "seat-password-secret"


def test_workshop_order_response_redacts_nested_metadata(
    client: TestClient, workshop: Workshop
) -> None:
    with patch.object(provisioning_service, "create_workshop_order", return_value=workshop):
        response = client.post(
            "/api/v1/workshops/orders",
            json={
                "tenant_id": "partner-a",
                "catalog_item_id": "catalog-1",
                "num_users": 1,
            },
        )

    assert response.status_code == 201
    _assert_secret_free(response.json())
