from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.api.deps import provisioning_service, public_access_service
from app.auth.oauth import User, get_current_user, require_admin
from app.domain.enums import SessionStatus
from app.domain.models import LabRequest, LabSession
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_state():
    provisioning_service._sessions.clear()
    provisioning_service._requests.clear()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def session() -> LabSession:
    session = LabSession(
        request_id="request-1",
        tenant_id="partner-a",
        catalog_item_id="catalog-1",
        namespace="seat-namespace",
        cluster_ref="arena",
        status=SessionStatus.READY,
        lab_url="https://lab.example.test",
        dashboard_url="https://dashboard.example.test",
        maas_api_key="sk-launchpad-do-not-return",
        resources={
            "showroom_enabled": True,
            "workspace_path": "/workspace",
            "sa_token": "service-account-secret",
            "credential_secret": "cluster-credential-secret",
            "nested": {
                "api_key": "nested-api-secret",
                "public_value": "preserve-me",
            },
            "items": [
                {"password": "nested-password", "name": "preserve-item"},
            ],
        },
        metadata={
            "purpose": "security-contract",
            "broker_token": "metadata-broker-secret",
            "nested": {"client_secret": "metadata-client-secret", "note": "safe"},
        },
    )
    provisioning_service._sessions[session.session_id] = session
    return session


@pytest.fixture
def partner_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: User(
        username="partner-user",
        tenant_ids=["partner-a"],
    )
    return TestClient(app)


def _assert_secret_free(payload: dict) -> None:
    rendered = str(payload)
    assert "maas_api_key" not in payload
    assert "sk-launchpad-do-not-return" not in rendered
    assert "service-account-secret" not in rendered
    assert "cluster-credential-secret" not in rendered
    assert "nested-api-secret" not in rendered
    assert "nested-password" not in rendered
    assert "metadata-broker-secret" not in rendered
    assert "metadata-client-secret" not in rendered

    assert payload["namespace"] == "seat-namespace"
    assert payload["cluster_ref"] == "arena"
    assert payload["lab_url"] == "https://lab.example.test"
    assert payload["dashboard_url"] == "https://dashboard.example.test"
    assert payload["resources"]["showroom_enabled"] is True
    assert payload["resources"]["workspace_path"] == "/workspace"
    assert payload["resources"]["nested"] == {"public_value": "preserve-me"}
    assert payload["resources"]["items"] == [{"name": "preserve-item"}]
    assert payload["metadata"] == {
        "purpose": "security-contract",
        "nested": {"note": "safe"},
    }


def test_session_list_and_detail_responses_are_secret_free(
    partner_client: TestClient,
    session: LabSession,
) -> None:
    listed = partner_client.get("/api/v1/lab-sessions")
    detailed = partner_client.get(f"/api/v1/lab-sessions/{session.session_id}")

    assert listed.status_code == 200
    assert detailed.status_code == 200
    _assert_secret_free(listed.json()[0])
    _assert_secret_free(detailed.json())


def test_public_session_service_model_is_secret_free(session: LabSession) -> None:
    public = provisioning_service.get_session_public(session.session_id)

    assert public is not None
    assert public.maas_api_key is None
    _assert_secret_free(public.model_dump())
    assert session.metadata["broker_token"] == "metadata-broker-secret"
    assert session.metadata["nested"]["client_secret"] == "metadata-client-secret"


def test_openapi_session_response_schema_has_no_maas_key() -> None:
    schema = app.openapi()["components"]["schemas"]["LabSessionResponse"]

    assert "maas_api_key" not in schema["properties"]


def test_request_list_and_detail_redact_metadata(
    partner_client: TestClient,
) -> None:
    request = LabRequest(
        tenant_id="partner-a",
        requester_id="partner-user",
        catalog_item_id="catalog-1",
        requested_mode="quick_start",
        metadata={
            "broker_token": "request-broker-secret",
            "nested": {"client_secret": "request-client-secret", "note": "safe"},
        },
    )
    provisioning_service._requests[request.request_id] = request

    listed = partner_client.get("/api/v1/lab-requests")
    detailed = partner_client.get(f"/api/v1/lab-requests/{request.request_id}")

    assert listed.status_code == 200
    assert detailed.status_code == 200
    for payload in (listed.json()[0], detailed.json()):
        assert "request-broker-secret" not in str(payload)
        assert "request-client-secret" not in str(payload)
        assert payload["metadata"] == {"nested": {"note": "safe"}}
    assert request.metadata["broker_token"] == "request-broker-secret"


def test_public_request_returns_code_only_on_create_with_safe_metadata(
    partner_client: TestClient,
) -> None:
    request = LabRequest(
        tenant_id="partner-a",
        requester_id="partner-user",
        catalog_item_id="catalog-1",
        requested_mode="quick_start",
        exposure_policy="public_code",
        metadata={"client_secret": "request-create-secret", "note": "safe"},
    )
    with (
        patch.object(provisioning_service, "submit_request", return_value=request),
        patch.object(
            public_access_service,
            "create_policy",
            return_value=(SimpleNamespace(public_url="https://labs.example.test/lab"), "one-code"),
        ),
    ):
        created = partner_client.post("/api/v1/lab-requests", json=request.model_dump(mode="json"))

    assert created.status_code == 201
    assert created.json()["one_time_access_code"] == "one-code"
    assert created.json()["public_url"] == "https://labs.example.test/lab"
    assert created.json()["metadata"] == {"note": "safe"}


@pytest.mark.parametrize("operation", ["validate", "activate", "reset", "reclaim"])
def test_session_mutation_responses_are_secret_free(
    partner_client: TestClient,
    session: LabSession,
    operation: str,
) -> None:
    with patch.object(provisioning_service, f"{operation}_session", return_value=session):
        response = partner_client.post(
            f"/api/v1/lab-sessions/{session.session_id}/{operation}"
        )

    assert response.status_code == 200
    _assert_secret_free(response.json())


def test_request_provision_response_is_secret_free(
    partner_client: TestClient,
    session: LabSession,
) -> None:
    request = type(
        "RequestRecord",
        (),
        {"request_id": session.request_id, "tenant_id": session.tenant_id},
    )()
    with (
        patch.dict("os.environ", {"LIFECYCLE_HA_ENABLED": "false"}),
        patch.object(provisioning_service, "get_request", return_value=request),
        patch.object(provisioning_service, "provision", return_value=session),
    ):
        response = partner_client.post(
            f"/api/v1/lab-requests/{session.request_id}/provision"
        )

    assert response.status_code == 201
    _assert_secret_free(response.json())


def test_admin_force_reclaim_response_is_secret_free(session: LabSession) -> None:
    app.dependency_overrides[require_admin] = lambda: User(
        username="admin",
        is_admin=True,
    )
    client = TestClient(app)

    with patch.object(
        provisioning_service,
        "force_reclaim_session",
        return_value=session,
    ):
        response = client.post(
            f"/api/v1/admin/sessions/{session.session_id}/force-reclaim"
        )

    assert response.status_code == 200
    _assert_secret_free(response.json())
