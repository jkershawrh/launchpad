from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.main import app


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts/portal-api-cdd-v1.yaml"
QUOTED_CALL = re.compile(
    r"(?:request(?:<[^;()]+>)?|fetch)\(\s*([`'\"])(.+?)\1",
    re.DOTALL,
)
TEMPLATE_VALUE = re.compile(r"\$\{[^}]+\}")


def _consumer_files() -> list[Path]:
    roots = (
        ROOT / "frontend/src/api",
        ROOT / "frontend/src/pages",
        ROOT / "frontend/src/components",
        ROOT / "admin/src/api",
        ROOT / "admin/src/pages",
    )
    return sorted(
        path
        for source_root in roots
        for path in source_root.rglob("*.ts*")
        if ".test." not in path.name
    )


def _normalize_consumer_path(value: str) -> str | None:
    if not value.startswith("/"):
        return None
    if value.startswith("/api/"):
        value = value[len("/api") :]
    value = value.split("?", 1)[0]
    value = TEMPLATE_VALUE.sub("{parameter}", value)
    return value


def _consumer_paths() -> dict[str, set[str]]:
    paths: dict[str, set[str]] = {}
    for source in _consumer_files():
        for match in QUOTED_CALL.finditer(source.read_text()):
            normalized = _normalize_consumer_path(match.group(2))
            if normalized:
                paths.setdefault(normalized, set()).add(str(source.relative_to(ROOT)))
    return paths


def _provider_operations() -> set[tuple[str, str]]:
    operations: set[tuple[str, str]] = set()
    for route, methods in app.openapi()["paths"].items():
        if not route.startswith("/api/v1/"):
            continue
        portal_route = route[len("/api/v1") :]
        for method in methods:
            if method.casefold() != "parameters":
                operations.add((method.upper(), portal_route))
    return operations


def _matches_provider(consumer: str, provider: str) -> bool:
    shape = lambda value: re.sub(r"\{[^/]+\}", "{}", value)
    return shape(consumer) == shape(provider)


def test_all_portal_paths_resolve_to_a_backend_provider() -> None:
    provider_paths = {path for _, path in _provider_operations()}
    missing = {
        consumer: sorted(sources)
        for consumer, sources in _consumer_paths().items()
        if not any(_matches_provider(consumer, provider) for provider in provider_paths)
    }
    assert missing == {}


def test_portals_never_duplicate_the_backend_version_prefix() -> None:
    duplicates = {
        path: sorted(sources)
        for path, sources in _consumer_paths().items()
        if path == "/v1" or path.startswith("/v1/")
    }
    assert duplicates == {}


def test_critical_mutation_methods_are_provided_by_openapi() -> None:
    contract = yaml.safe_load(CONTRACT.read_text())
    providers = _provider_operations()
    missing = []
    for operation in contract["critical_mutations"]:
        expected = (operation["method"].upper(), operation["path"])
        if expected not in providers:
            missing.append(expected)
    assert missing == []


def test_both_portals_share_the_versioned_proxy_contract() -> None:
    for relative_path in ("frontend/nginx.conf", "admin/nginx.conf"):
        config = (ROOT / relative_path).read_text()
        assert "location /api/" in config
        assert "proxy_pass http://backend:8000/api/v1/;" in config
