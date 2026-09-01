from fastapi.testclient import TestClient

from app.public_gateway import app


def test_gateway_exposes_only_public_health_identity():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "public-access-gateway"}


def test_gateway_has_no_openapi_or_admin_surface():
    client = TestClient(app)
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/admin").status_code == 404
