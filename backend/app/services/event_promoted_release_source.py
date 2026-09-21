"""Local, fail-closed adapter for authenticated promoted catalog releases.

The signing key and policy path must be supplied by the server operator, not an
order or a health probe. This adapter verifies a complete immutable runtime
image inventory and per-image release receipts; it does not query Quay or prove
that the current policy's provisional authority is production approved.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.services.catalog_supply_chain import (
    IMMUTABLE_IMAGE,
    evaluate_artifact_release_evidence,
)
from app.services.event_artifact_requirements import TrustedReleaseManifest

SCHEMA_VERSION = "launchpad.redhat.com/promoted-catalog-release/v1"
_IDENTITY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PromotedReleaseSourceError(ValueError):
    """An existing release cannot be trusted as an admission input."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PromotedReleaseSourceError(f"duplicate release field: {key}")
        result[key] = value
    return result


def _safe_relative(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise PromotedReleaseSourceError("release evidence path is unsafe")
    path = root / relative
    component = root
    for part in Path(relative).parts:
        component = component / part
        if component.is_symlink():
            raise PromotedReleaseSourceError("release evidence path contains a symlink")
    if not path.resolve().is_relative_to(root.resolve()):
        raise PromotedReleaseSourceError("release evidence path escapes release root")
    return path


class AuthenticatedPromotedReleaseSource:
    """Resolve signed local promotion records for the event requirements API.

    Record layout: root/<catalog_id>/<catalog_release>/release.json and
    release.sig (hex HMAC-SHA256 of the exact JSON bytes). A trusted promoter
    must enumerate *all* runtime images and bind one valid release evidence
    receipt to each image. No digest is inferred from catalog metadata.
    """

    def __init__(self, root: Path | str, policy_path: Path | str, signing_key: bytes):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("a server-owned signing key of at least 32 bytes is required")
        self.root = Path(root)
        self.policy_path = Path(policy_path)
        self._signing_key = signing_key

    def get_promoted_release(
        self, catalog_id: str, catalog_release: str
    ) -> TrustedReleaseManifest | None:
        if not _IDENTITY.fullmatch(catalog_id) or not _IDENTITY.fullmatch(catalog_release):
            raise PromotedReleaseSourceError("invalid catalog release identity")
        catalog_directory = self.root / catalog_id
        directory = catalog_directory / catalog_release
        if any(component.is_symlink() for component in (self.root, catalog_directory, directory)):
            raise PromotedReleaseSourceError("release path contains a symlink")
        if not directory.exists():
            return None
        try:
            if directory.is_symlink() or not directory.is_dir():
                raise PromotedReleaseSourceError("release directory is not trusted")
            policy = yaml.safe_load(self.policy_path.read_text())
            if not isinstance(policy, dict):
                raise PromotedReleaseSourceError("registry policy is missing or invalid")
            authority = policy.get("authority") or {}
            signing = policy.get("signing") or {}
            if authority.get("organization_ownership_approved") is not True:
                raise PromotedReleaseSourceError("registry ownership is not approved")
            if authority.get("state") != "approved":
                raise PromotedReleaseSourceError("registry authority is not approved")
            if signing.get("identity_approved") is not True:
                raise PromotedReleaseSourceError("release signing identity is not approved")
            origin = authority.get("origin")
            if not isinstance(origin, str) or not origin or "://" in origin or "@" in origin:
                raise PromotedReleaseSourceError("registry origin is invalid")

            manifest_path = _safe_relative(directory, "release.json")
            signature_path = _safe_relative(directory, "release.sig")
            raw = manifest_path.read_bytes()
            signature = signature_path.read_text().strip()
            expected_signature = hmac.new(self._signing_key, raw, hashlib.sha256).hexdigest()
            if not _SHA256.fullmatch(signature) or not hmac.compare_digest(
                signature, expected_signature
            ):
                raise PromotedReleaseSourceError("release signature is invalid")
            manifest = json.loads(raw, object_pairs_hook=_unique_object)
            if not isinstance(manifest, dict) or set(manifest) != {
                "schema_version",
                "catalog_id",
                "catalog_release",
                "state",
                "runtime_images_complete",
                "runtime_images",
                "image_evidence",
            }:
                raise PromotedReleaseSourceError("release manifest has missing or unknown fields")
            if manifest["schema_version"] != SCHEMA_VERSION:
                raise PromotedReleaseSourceError("release schema is unsupported")
            if (manifest["catalog_id"], manifest["catalog_release"]) != (
                catalog_id,
                catalog_release,
            ):
                raise PromotedReleaseSourceError("release identity does not match lookup")
            if manifest["state"] != "promoted" or manifest["runtime_images_complete"] is not True:
                raise PromotedReleaseSourceError(
                    "release is not promoted with complete runtime images"
                )
            images = manifest["runtime_images"]
            if not isinstance(images, list) or not images or len(images) != len(set(images)):
                raise PromotedReleaseSourceError("runtime image inventory is missing or duplicated")
            if any(
                not isinstance(image, str)
                or not IMMUTABLE_IMAGE.fullmatch(image)
                or not image.startswith(origin + "/")
                for image in images
            ):
                raise PromotedReleaseSourceError(
                    "runtime image is mutable or outside approved origin"
                )
            receipts = manifest["image_evidence"]
            if not isinstance(receipts, list) or len(receipts) != len(images):
                raise PromotedReleaseSourceError("release receipts do not cover runtime images")
            evidence_images: list[str] = []
            for item in receipts:
                if not isinstance(item, dict) or set(item) != {"image", "path", "sha256"}:
                    raise PromotedReleaseSourceError("release receipt reference is invalid")
                image, path, digest = item["image"], item["path"], item["sha256"]
                if (
                    not isinstance(image, str)
                    or not isinstance(path, str)
                    or not isinstance(digest, str)
                    or not _SHA256.fullmatch(digest)
                ):
                    raise PromotedReleaseSourceError("release receipt reference is malformed")
                receipt_path = _safe_relative(directory, path)
                receipt_bytes = receipt_path.read_bytes()
                if not hmac.compare_digest(hashlib.sha256(receipt_bytes).hexdigest(), digest):
                    raise PromotedReleaseSourceError("release receipt digest mismatch")
                report = evaluate_artifact_release_evidence(self.policy_path, receipt_path)
                if not report["eligible"] or report["image"] != image:
                    raise PromotedReleaseSourceError("release receipt is invalid or mismatched")
                repository_contract = (policy.get("repositories") or {}).get(
                    report["component"]
                ) or {}
                if repository_contract.get("pull_grant_verified") is not True:
                    raise PromotedReleaseSourceError("registry pull grant is not verified")
                evidence_images.append(image)
            if set(evidence_images) != set(images) or len(evidence_images) != len(
                set(evidence_images)
            ):
                raise PromotedReleaseSourceError(
                    "release receipts do not exactly cover runtime images"
                )
            return TrustedReleaseManifest(
                catalog_id=catalog_id,
                catalog_release=catalog_release,
                image_refs=sorted(images),
                promotion_evidence_id="sha256:" + hashlib.sha256(raw).hexdigest(),
            )
        except PromotedReleaseSourceError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise PromotedReleaseSourceError(
                "promoted release evidence cannot be verified"
            ) from exc
