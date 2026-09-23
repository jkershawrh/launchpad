"""Review a pinned local Helm source without publishing or deploying it.

This is a developer preflight, not the trusted isolated renderer or a release
receipt. It never emits raw manifests, command output, or provider errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.catalog_intake_render_review import (
    MAX_RENDERED_BYTES,
    _manifest_findings,
    _UniqueKeyLoader,
)
from app.services.catalog_onboarding import _walk_mappings, load_intake

SCHEMA = "launchpad.redhat.com/catalog-intake-offline-render/v1"
REVISION = re.compile(r"^[0-9a-f]{40}$")
CATALOG_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_IMAGE = re.compile(r"^[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}$")
SAFE_SECRET_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,251}[a-z0-9])?$")
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _report(catalog_id: str, revision: str, findings: list[str]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "mode": "offline-local-render",
        "catalog_item_id": catalog_id,
        "revision": revision,
        "status": "blocked",
        "findings": findings,
        "resource_count": 0,
        "image_count": 0,
        "manifest_sha256": None,
        "helm_values_sha256": None,
        "image_override_applied": False,
        "release_eligible": False,
    }


def _reviewed_values(intake: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    runtime = intake.get("runtime")
    if not isinstance(runtime, dict):
        return {}, False
    workload = runtime.get("workload", {})
    if not isinstance(workload, dict):
        return {}, False
    values = workload.get("helm_values", {})
    if not isinstance(values, dict) or set(values) - {"app", "model"}:
        return {}, False
    reviewed: dict[str, Any] = {}
    if "app" in values:
        app = values["app"]
        if not isinstance(app, dict) or set(app) != {"image"}:
            return {}, False
        image = app["image"]
        if not isinstance(image, str) or len(image) > 512 or not SAFE_IMAGE.fullmatch(image):
            return {}, False
        reviewed["app"] = {"image": image}
    if "model" in values:
        if values["model"] != {"endpointFromSecret": True}:
            return {}, False
        secret = workload.get("runtime_secret_name")
        if not isinstance(secret, str) or not SAFE_SECRET_NAME.fullmatch(secret):
            return {}, False
        reviewed["model"] = {"endpointFromSecret": True, "existingSecret": secret}
    return reviewed, True


def _helm_values_digest(values: dict[str, Any]) -> str:
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _rendered_image_present(output: bytes, image: str) -> bool:
    documents = yaml.load_all(output.decode("utf-8"), Loader=_UniqueKeyLoader)
    return any(
        mapping.get("image") == image
        for document in documents
        if isinstance(document, dict)
        for mapping in _walk_mappings(document)
    )


def _rendered_secret_refs_present(output: bytes, secret: str) -> bool:
    documents = yaml.load_all(output.decode("utf-8"), Loader=_UniqueKeyLoader)
    keys = {
        mapping.get("key")
        for document in documents
        if isinstance(document, dict)
        for mapping in _walk_mappings(document)
        if mapping.get("name") == secret and "key" in mapping
    }
    return {"endpoint", "name", "api-key"} <= keys


def _run(runner: Runner, command: list[str], source: Path) -> subprocess.CompletedProcess:
    return runner(
        command,
        cwd=str(source),
        capture_output=True,
        timeout=30,
        check=False,
    )


def review(
    intake_path: Path,
    source_dir: Path,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Return sanitized local findings for exactly the intake's pinned source."""

    try:
        intake = load_intake(intake_path)
    except Exception:  # noqa: BLE001 - submitted files may contain private values
        return _report("", "", ["intake-unavailable"])
    catalog = intake.get("catalog")
    catalog_id = str(catalog.get("catalog_item_id", "")) if isinstance(catalog, dict) else ""
    if not CATALOG_ID.fullmatch(catalog_id):
        catalog_id = ""
    sources = intake.get("sources")
    workload = sources.get("workload") if isinstance(sources, dict) else None
    if not isinstance(workload, dict):
        workload = {}
    revision = str(workload.get("revision", ""))
    if not REVISION.fullmatch(revision):
        return _report(catalog_id, "", ["source-revision-invalid"])
    runtime = intake.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("deployment_type") != "helm":
        return _report(catalog_id, revision, ["unsupported-package"])
    reviewed_values, override_valid = _reviewed_values(intake)
    if not override_valid:
        return _report(catalog_id, revision, ["helm-values-unsupported-or-unsafe"])
    image = reviewed_values.get("app", {}).get("image")
    secret = reviewed_values.get("model", {}).get("existingSecret")

    deploy_path = workload.get("deploy_path")
    source = source_dir.resolve()
    if (
        not isinstance(deploy_path, str)
        or not deploy_path
        or Path(deploy_path).is_absolute()
        or ".." in Path(deploy_path).parts
        or not source.is_dir()
    ):
        return _report(catalog_id, revision, ["chart-path-invalid"])
    chart = (source / deploy_path).resolve()
    if not chart.is_relative_to(source) or not (chart / "Chart.yaml").is_file():
        return _report(catalog_id, revision, ["chart-path-invalid"])

    try:
        head = _run(runner, ["git", "rev-parse", "HEAD"], source)
        if head.returncode != 0 or head.stdout.decode().strip() != revision:
            return _report(catalog_id, revision, ["source-revision-mismatch"])
        dirty = _run(runner, ["git", "status", "--porcelain", "--untracked-files=all"], source)
        if dirty.returncode != 0 or dirty.stdout.strip():
            return _report(catalog_id, revision, ["source-dirty"])
        lint = _run(runner, ["helm", "lint", str(chart), "--strict"], source)
        if lint.returncode != 0:
            return _report(catalog_id, revision, ["helm-lint-failed"])
        command = [
            "helm",
            "template",
            "launchpad-intake",
            str(chart),
            "--namespace",
            "launchpad-intake-review",
        ]
        if image:
            command.extend(["--set-string", "app.image=" + image])
        if secret:
            command.extend(["--set", "model.endpointFromSecret=true"])
            command.extend(["--set-string", "model.existingSecret=" + secret])
        rendered = _run(runner, command, source)
        if rendered.returncode != 0:
            return _report(catalog_id, revision, ["helm-render-failed"])
        if not rendered.stdout or len(rendered.stdout) > MAX_RENDERED_BYTES:
            return _report(catalog_id, revision, ["render-output-size-invalid"])
        findings, resource_count, image_count = _manifest_findings(rendered.stdout)
        if image and not findings and not _rendered_image_present(rendered.stdout, image):
            findings.append("image-override-not-rendered")
        if secret and not findings and not _rendered_secret_refs_present(rendered.stdout, secret):
            findings.append("model-secret-override-not-rendered")
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError, ValueError):
        return _report(catalog_id, revision, ["local-render-unavailable"])
    except Exception:  # noqa: BLE001 - provider errors must never enter the report
        return _report(catalog_id, revision, ["local-render-unavailable"])

    report = _report(catalog_id, revision, findings)
    report.update(
        status="blocked" if findings else "review-ready-local",
        resource_count=resource_count,
        image_count=image_count,
        manifest_sha256="sha256:" + hashlib.sha256(rendered.stdout).hexdigest(),
        helm_values_sha256=_helm_values_digest(reviewed_values),
        image_override_applied=bool(image),
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intake", type=Path)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    report = review(args.intake, args.source)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "review-ready-local" else 2


if __name__ == "__main__":
    raise SystemExit(main())
