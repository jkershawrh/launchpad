"""Deployment contracts for the operator-facing admin frontend."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_admin_api_proxy_preserves_backend_v1_contract() -> None:
    """Browser /api/* calls must arrive at the backend's /api/v1/* router."""

    nginx = (ROOT / "admin/nginx.conf").read_text()

    assert "location /api/" in nginx
    assert "proxy_pass http://backend:8000/api/v1/;" in nginx
