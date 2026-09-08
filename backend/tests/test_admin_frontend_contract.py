"""Deployment contracts for the operator-facing admin frontend."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_admin_api_proxy_preserves_backend_v1_contract() -> None:
    """Browser /api/* calls must arrive at the backend's /api/v1/* router."""

    nginx = (ROOT / "admin/nginx.conf").read_text()

    assert "location /api/" in nginx
    assert "proxy_pass http://backend:8000/api/v1/;" in nginx


def test_admin_system_page_uses_openshift_health_contracts() -> None:
    """The cluster deployment must not report local Podman as platform health."""

    client = (ROOT / "admin/src/api/client.ts").read_text()
    page = (ROOT / "admin/src/pages/SystemStatus.tsx").read_text()

    assert "getDetailedSystemHealth" in client
    assert "'/admin/system/health'" in client
    assert "getClusterPreflight" in client
    assert "'/admin/clusters/preflight'" in client
    assert "Infrastructure health and execution cluster readiness." in page
    assert "container management" not in page.lower()


def test_admin_labels_bounded_and_estimated_data_honestly() -> None:
    dashboard = (ROOT / "admin/src/pages/Dashboard.tsx").read_text()
    reports = (ROOT / "admin/src/pages/Reports.tsx").read_text()

    assert "{ label: 'Recent Sessions'" in dashboard
    assert "Recent Sessions by Tenant" in dashboard
    assert "Estimated showback" in reports
    assert "measured per-seat telemetry is connected" in reports


def test_admin_uses_partner_launchpad_dark_theme_contract() -> None:
    """The admin content must share the requester portal's dark visual language."""

    styles = (ROOT / "admin/src/index.css").read_text()
    layout = (ROOT / "admin/src/components/AdminLayout.tsx").read_text()

    assert "--brand-dark: #151515" in styles
    assert "--brand-surface: #212121" in styles
    assert "--brand-border-light: #333" in styles
    assert "--brand-link: #58A6E7" in styles
    assert '.admin-shell main [class~="bg-white"]' in styles
    assert '.admin-shell main [class~="text-[#151515]"]' in styles
    assert 'className="admin-shell min-h-screen' in layout
    assert "Launchpad Operations" in layout
