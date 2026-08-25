from fastapi.testclient import TestClient

from app.api.deps import provisioning_service, tenant_store
from app.auth.oauth import User, get_current_user
from app.domain.enums import CatalogCategory, TenantType
from app.domain.models import LabRequest, Tenant
from app.main import app


def _client(user: User) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def setup_function():
    tenant_store._tenants.clear()
    provisioning_service._requests.clear()
    provisioning_service._sessions.clear()
    app.dependency_overrides.clear()
    for tenant_id in ("partner-a", "partner-b"):
        tenant_store.create(Tenant(
            tenant_id=tenant_id,
            display_name=tenant_id,
            tenant_type=TenantType.PARTNER,
        ))


def teardown_function():
    app.dependency_overrides.clear()


def _request(tenant_id: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "requester_id": "partner-user",
        "catalog_item_id": "inference-overdrive-quickstart",
        "requested_mode": "quick_start",
    }


def test_partner_only_lists_assigned_tenants():
    client = _client(User(username="partner-user", tenant_ids=["partner-a"]))

    response = client.get("/api/v1/tenants")

    assert response.status_code == 200
    assert [tenant["tenant_id"] for tenant in response.json()] == ["partner-a"]


def test_partner_cannot_create_request_for_another_tenant():
    client = _client(User(username="partner-user", tenant_ids=["partner-a"]))

    response = client.post("/api/v1/lab-requests", json=_request("partner-b"))

    assert response.status_code == 403


def test_partner_can_create_request_for_assigned_tenant():
    client = _client(User(username="partner-user", tenant_ids=["partner-a"]))

    response = client.post("/api/v1/lab-requests", json=_request("partner-a"))

    assert response.status_code == 201
    assert response.json()["tenant_id"] == "partner-a"


def test_partner_cannot_read_or_mutate_another_tenants_session():
    request = provisioning_service.submit_request(LabRequest(
        tenant_id="partner-b",
        requester_id="other-user",
        catalog_item_id="inference-overdrive-quickstart",
        requested_mode=CatalogCategory.QUICK_START,
    ))
    session = provisioning_service.provision(request.request_id)
    client = _client(User(username="partner-user", tenant_ids=["partner-a"]))

    assert client.get(f"/api/v1/lab-sessions/{session.session_id}").status_code == 404
    assert client.post(f"/api/v1/lab-sessions/{session.session_id}/validate").status_code == 404


def test_admin_retains_cross_tenant_access():
    client = _client(User(username="admin", is_admin=True))

    response = client.post("/api/v1/lab-requests", json=_request("partner-b"))

    assert response.status_code == 201
