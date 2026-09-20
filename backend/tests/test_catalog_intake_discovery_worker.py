from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app import catalog_intake_worker_main
from app.domain.catalog_intake_discovery import (
    CatalogIntakeDiscoveryRequest,
    CatalogIntakeSourceApproval,
)
from app.services.catalog_intake_discovery import CatalogIntakeDiscoveryRunner
from pydantic import ValidationError

REPOSITORY = "https://github.com/example/quickstart.git"
REVISION = "a" * 40


def _quickstart(root: Path) -> Path:
    source = root / "fixture"
    pages = source / "showroom/modules/ROOT/pages"
    pages.mkdir(parents=True)
    (source / "site.yml").write_text(
        "content:\n  sources:\n    - url: .\n      start_path: showroom\n",
        encoding="utf-8",
    )
    (source / "showroom/antora.yml").write_text(
        "name: example\ntitle: Example\nversion: ~\n",
        encoding="utf-8",
    )
    (pages / "index.adoc").write_text("= Start\n", encoding="utf-8")
    chart = source / "deploy/chart"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: example\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    (chart / "values.yaml").write_text("{}\n", encoding="utf-8")
    return source


def _request() -> CatalogIntakeDiscoveryRequest:
    return CatalogIntakeDiscoveryRequest(
        intake_id="intake-example",
        attempt_id="attempt-001",
        repository_url=REPOSITORY,
        revision=REVISION,
        catalog_item_id="example-quickstart",
        display_name="Example Quickstart",
        policy_version="1.0.0",
        source_approval_id="approval-001",
        worker_image_digest="sha256:" + "b" * 64,
    )


def _approval() -> CatalogIntakeSourceApproval:
    return CatalogIntakeSourceApproval(
        approval_id="approval-001",
        repository_url=REPOSITORY,
        revision=REVISION,
        requested_by="solution-owner",
        approved_by="catalog-reviewer",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        expires_at=datetime(2100, 1, 1, tzinfo=UTC),
        purpose="Quickstart discovery",
    )


def _checkout_from(source: Path):
    def checkout(_repository: str, _revision: str, destination: Path) -> None:
        shutil.copytree(source, destination)

    return checkout


def test_discovery_runner_generates_sanitized_draft_and_cleanup_receipt(
    tmp_path: Path,
) -> None:
    source = _quickstart(tmp_path)
    workspaces = tmp_path / "workspaces"
    runner = CatalogIntakeDiscoveryRunner(
        source_approvals=[_approval()],
        checkout=_checkout_from(source),
        workspace_parent=workspaces,
    )

    receipt = runner.run(_request())

    assert receipt.status == "passed"
    assert receipt.draft_intake is not None
    assert receipt.draft_intake["catalog"]["status"] == "draft"
    assert receipt.draft_intake["certification"]["max_workshop_seats"] == 1
    assert receipt.cleanup.workspace_removed is True
    assert receipt.cleanup.result == "pass"
    assert list(workspaces.iterdir()) == []
    assert receipt.output_hash.startswith("sha256:")
    assert receipt.idempotency_key.startswith("sha256:")


def test_discovery_runner_denies_unapproved_repository_without_checkout(
    tmp_path: Path,
) -> None:
    checkout_called = False

    def checkout(*_args) -> None:
        nonlocal checkout_called
        checkout_called = True

    runner = CatalogIntakeDiscoveryRunner(
        source_approvals=[],
        checkout=checkout,
        workspace_parent=tmp_path,
    )

    receipt = runner.run(_request())

    assert receipt.status == "denied"
    assert receipt.error_codes == ["source-not-approved"]
    assert checkout_called is False
    assert receipt.draft_intake is None


def test_discovery_runner_denies_approval_for_a_different_revision(
    tmp_path: Path,
) -> None:
    checkout_called = False

    def checkout(*_args) -> None:
        nonlocal checkout_called
        checkout_called = True

    approval = _approval().model_copy(update={"revision": "c" * 40})
    runner = CatalogIntakeDiscoveryRunner(
        source_approvals=[approval],
        checkout=checkout,
        workspace_parent=tmp_path,
    )

    receipt = runner.run(_request())

    assert receipt.status == "denied"
    assert receipt.error_codes == ["source-not-approved"]
    assert checkout_called is False


def test_discovery_runner_rejects_source_secret_without_leaking_it(
    tmp_path: Path,
) -> None:
    source = _quickstart(tmp_path)
    leaked = "sk-live-do-not-record-this-value"
    (source / "credentials.txt").write_text(leaked, encoding="utf-8")
    runner = CatalogIntakeDiscoveryRunner(
        source_approvals=[_approval()],
        checkout=_checkout_from(source),
        workspace_parent=tmp_path / "workspaces",
    )

    receipt = runner.run(_request())
    rendered = receipt.model_dump_json()

    assert receipt.status == "denied"
    assert receipt.error_codes == ["source-secret-detected"]
    assert leaked not in rendered
    assert "credentials.txt" not in rendered
    assert receipt.cleanup.workspace_removed is True


def test_discovery_runner_scans_the_entire_source_file(tmp_path: Path) -> None:
    source = _quickstart(tmp_path)
    leaked = b"ghp_" + (b"z" * 36)
    (source / "large.bin").write_bytes((b"x" * (1024 * 1024 + 100)) + leaked)
    runner = CatalogIntakeDiscoveryRunner(
        source_approvals=[_approval()],
        checkout=_checkout_from(source),
        workspace_parent=tmp_path / "workspaces",
    )

    receipt = runner.run(_request())

    assert receipt.status == "denied"
    assert receipt.error_codes == ["source-secret-detected"]
    assert leaked.decode() not in receipt.model_dump_json()


def test_discovery_runner_allows_explicit_documentation_placeholder(
    tmp_path: Path,
) -> None:
    source = _quickstart(tmp_path)
    (source / "README.md").write_text(
        'token: "ghp_your_personal_access_token"\n'
        'Authorization: "Bearer test-token"\n',
        encoding="utf-8",
    )
    runner = CatalogIntakeDiscoveryRunner(
        source_approvals=[_approval()],
        checkout=_checkout_from(source),
        workspace_parent=tmp_path / "workspaces",
    )

    receipt = runner.run(_request())

    assert receipt.status == "passed"
    assert receipt.scan_summary["files_scanned"] > 0


def test_discovery_idempotency_key_is_stable_for_same_source_and_policy() -> None:
    first = _request()
    second = _request().model_copy(update={"attempt_id": "attempt-002"})

    assert first.idempotency_key() == second.idempotency_key()


def test_discovery_request_rejects_mutable_source_and_credential_fields() -> None:
    payload = _request().model_dump()
    payload["revision"] = "main"
    payload["api_token"] = "must-not-enter-worker"

    with pytest.raises(ValidationError):
        CatalogIntakeDiscoveryRequest.model_validate(payload)

    with pytest.raises(ValidationError, match="separation of duties"):
        CatalogIntakeSourceApproval.model_validate(
            _approval().model_dump() | {"approved_by": "solution-owner"}
        )


def test_discovery_runner_rejects_secret_like_payload_before_checkout(
    tmp_path: Path,
) -> None:
    checkout_called = False

    def checkout(*_args) -> None:
        nonlocal checkout_called
        checkout_called = True

    request = _request().model_copy(
        update={"display_name": "sk-do-not-dispatch-this-secret"}
    )
    receipt = CatalogIntakeDiscoveryRunner(
        source_approvals=[_approval()],
        checkout=checkout,
        workspace_parent=tmp_path,
    ).run(request)

    assert receipt.status == "denied"
    assert receipt.error_codes == ["payload-secret-detected"]
    assert checkout_called is False
    assert "do-not-dispatch" not in receipt.model_dump_json()


def test_worker_bootstrap_failure_never_echoes_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sensitive = "must-not-be-printed"
    monkeypatch.setenv("CATALOG_INTAKE_REQUEST_JSON", "{" + sensitive)

    assert catalog_intake_worker_main.main() == 2
    output = capsys.readouterr().out
    assert sensitive not in output
    assert "worker-bootstrap-failed" in output
