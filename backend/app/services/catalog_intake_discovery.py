from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.domain.catalog_intake_discovery import (
    CatalogIntakeCleanupReceipt,
    CatalogIntakeDiscoveryReceipt,
    CatalogIntakeDiscoveryRequest,
    CatalogIntakeSourceApproval,
)
from app.services.catalog_onboarding import discover_quickstart_repo

Checkout = Callable[[str, str, Path], None]
Scanner = Callable[[Path], tuple[int, int]]
MAX_WORKSPACE_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
SECRET_PATTERNS = (
    re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?" + b"PRIVATE" + rb"\s+" + b"KEY-----"
    ),
    re.compile(
        rb"(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
    ),
    re.compile(rb"\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b", re.IGNORECASE),
)
PLACEHOLDER_CREDENTIALS = (
    re.compile(
        rb"(?:sk-|ghp_|github_pat_)(?:your|example|fake|placeholder|replace|x{8,})[A-Za-z0-9_-]*$",
        re.IGNORECASE,
    ),
    re.compile(
        rb"Bearer\s+(?:your|example|fake|placeholder|replace|test|valid|invalid|expired|x{8,})[A-Za-z0-9._~+/-]*$",
        re.IGNORECASE,
    ),
)


def _contains_secret(payload: bytes) -> bool:
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(payload):
            if any(
                placeholder.fullmatch(match.group())
                for placeholder in PLACEHOLDER_CREDENTIALS
            ):
                continue
            return True
    return False


class SourcePolicyDeniedError(ValueError):
    pass


class SourceSecretDetectedError(ValueError):
    pass


class SourceScannerFailedError(RuntimeError):
    pass


def checkout_immutable_github_source(
    repository_url: str,
    revision: str,
    destination: Path,
) -> None:
    """Fetch exactly one approved GitHub commit without invoking a shell."""

    destination.mkdir(parents=True, exist_ok=False)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
    }
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE"):
        if name in os.environ:
            env[name] = os.environ[name]

    def run(*arguments: str) -> str:
        completed = subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=never",
                "-c",
                "http.followRedirects=false",
                *arguments,
            ],
            cwd=destination,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=240,
        )
        return completed.stdout.strip()

    run("init", "--quiet")
    run("remote", "add", "origin", repository_url)
    run("fetch", "--quiet", "--depth", "1", "--no-tags", "origin", revision)
    run("checkout", "--quiet", "--detach", "FETCH_HEAD")
    if run("rev-parse", "HEAD") != revision:
        raise SourcePolicyDeniedError("immutable-revision-mismatch")


def _scan_workspace(root: Path) -> tuple[int, int]:
    file_count = 0
    byte_count = 0
    try:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise SourcePolicyDeniedError("source-symlink-denied")
            if not path.is_file() or ".git" in path.parts:
                continue
            file_count += 1
            size = path.stat().st_size
            byte_count += size
            if byte_count > MAX_WORKSPACE_BYTES:
                raise SourcePolicyDeniedError("source-size-exceeded")
            with path.open("rb") as handle:
                previous = b""
                while chunk := handle.read(64 * 1024):
                    sample = previous + chunk
                    if _contains_secret(sample):
                        raise SourceSecretDetectedError("source-secret-detected")
                    previous = sample[-256:]
    except OSError as exc:
        raise SourceScannerFailedError("source-scan-failed") from exc
    return file_count, byte_count


def _safe_output(draft: dict) -> tuple[str, bytes]:
    encoded = json.dumps(draft, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise SourcePolicyDeniedError("sanitized-output-size-exceeded")
    if _contains_secret(encoded):
        raise SourceSecretDetectedError("output-secret-detected")
    return "sha256:" + hashlib.sha256(encoded).hexdigest(), encoded


def _request_contains_secret(request: CatalogIntakeDiscoveryRequest) -> bool:
    encoded = request.model_dump_json().encode()
    return _contains_secret(encoded)


class CatalogIntakeDiscoveryRunner:
    """Credential-free repository analyzer with bounded, sanitized output."""

    def __init__(
        self,
        *,
        source_approvals: list[CatalogIntakeSourceApproval],
        workspace_parent: Path,
        checkout: Checkout = checkout_immutable_github_source,
        scan: Scanner = _scan_workspace,
    ) -> None:
        self.source_approvals = {
            approval.approval_id: approval for approval in source_approvals
        }
        self.workspace_parent = workspace_parent
        self.checkout = checkout
        self.scan = scan

    def _source_is_approved(
        self,
        request: CatalogIntakeDiscoveryRequest,
        *,
        now: datetime,
    ) -> bool:
        approval = self.source_approvals.get(request.source_approval_id)
        if approval is None:
            return False
        approved_at = approval.approved_at
        expires_at = approval.expires_at
        if approved_at.tzinfo is None:
            approved_at = approved_at.replace(tzinfo=UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return (
            approval.repository_url == request.repository_url
            and approval.revision == request.revision
            and approved_at <= now < expires_at
        )

    @staticmethod
    def _cleanup_receipt(
        request: CatalogIntakeDiscoveryRequest,
        *,
        workspace_removed: bool,
        bytes_removed: int,
    ) -> CatalogIntakeCleanupReceipt:
        digest = hashlib.sha256(
            f"{request.attempt_id}:cleanup:{workspace_removed}".encode()
        ).hexdigest()
        return CatalogIntakeCleanupReceipt(
            receipt_id="sha256:" + digest,
            attempt_id=request.attempt_id,
            workspace_removed=workspace_removed,
            bytes_removed=bytes_removed,
            result="pass" if workspace_removed else "fail",
        )

    def run(self, request: CatalogIntakeDiscoveryRequest) -> CatalogIntakeDiscoveryReceipt:
        started = datetime.now(UTC)
        draft = None
        output_hash = None
        error_codes: list[str] = []
        status = "failed"
        file_count = 0
        byte_count = 0
        workspace_removed = True

        if _request_contains_secret(request):
            status = "denied"
            error_codes = ["payload-secret-detected"]
        elif not self._source_is_approved(request, now=started):
            status = "denied"
            error_codes = ["source-not-approved"]
        else:
            self.workspace_parent.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(
                prefix=f"{request.attempt_id}-",
                dir=self.workspace_parent,
            )
            workspace = Path(temporary.name)
            source = workspace / "source"
            try:
                self.checkout(request.repository_url, request.revision, source)
                file_count, byte_count = self.scan(source)
                draft, report = discover_quickstart_repo(
                    source,
                    repo_url=request.repository_url,
                    revision=request.revision,
                    catalog_id=request.catalog_item_id,
                    display_name=request.display_name,
                )
                if report["discovery_status"] != "pass":
                    status = "failed"
                    error_codes = ["repository-discovery-failed"]
                    draft = None
                else:
                    output_hash, _ = _safe_output(draft)
                    status = "passed"
            except SourceSecretDetectedError as exc:
                status = "denied"
                error_codes = [str(exc)]
                draft = None
            except SourcePolicyDeniedError as exc:
                status = "denied"
                error_codes = [str(exc)]
                draft = None
            except SourceScannerFailedError:
                status = "failed"
                error_codes = ["source-scan-failed"]
                draft = None
            except Exception:  # noqa: BLE001 - receipt must not leak failure detail
                status = "failed"
                error_codes = ["worker-execution-failed"]
                draft = None
            finally:
                temporary.cleanup()
                workspace_removed = not workspace.exists()

        finished = datetime.now(UTC)
        return CatalogIntakeDiscoveryReceipt(
            intake_id=request.intake_id,
            attempt_id=request.attempt_id,
            idempotency_key=request.idempotency_key(),
            repository_url=request.repository_url,
            revision=request.revision,
            policy_version=request.policy_version,
            source_approval_id=request.source_approval_id,
            worker_image_digest=request.worker_image_digest,
            started_at=started,
            finished_at=finished,
            status=status,
            error_codes=error_codes,
            scan_summary={"files_scanned": file_count, "bytes_scanned": byte_count},
            output_hash=output_hash,
            draft_intake=draft,
            cleanup=self._cleanup_receipt(
                request,
                workspace_removed=workspace_removed,
                bytes_removed=byte_count,
            ),
        )
