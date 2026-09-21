"""Local contract tests for the authenticated promoted-release boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
import yaml
from app.services.event_promoted_release_source import (
    AuthenticatedPromotedReleaseSource,
    PromotedReleaseSourceError,
)

IMAGE = "quay.io/example/serve@sha256:" + "a" * 64
KEY = b"trusted-test-key-material-32-bytes!!"
ROOT = Path(__file__).resolve().parents[2]


def _receipt(image: str = IMAGE) -> dict:
    checks = {
        name: {"status": "passed", "evidence": ["evidence://proof"]}
        for name in (
            "vulnerability_scan",
            "sbom",
            "signature",
            "provenance",
            "license_policy",
            "retention",
        )
    }
    checks["vulnerability_scan"].update(critical_findings=0, high_findings=0)
    checks["sbom"].update(artifact="oci://sbom", sha256="b" * 64)
    checks["signature"].update(identity="trusted-ci", subject_image=image, verified=True)
    checks["provenance"].update(
        artifact="oci://provenance",
        sha256="c" * 64,
        subject_image=image,
        source_repository="https://example/repo",
        source_revision="d" * 40,
        builder_identity="trusted-ci",
        verified=True,
    )
    checks["retention"].update(protected_until="2027-12-01T00:00:00Z", rollback_releases_retained=3)
    return {
        "schema_version": "launchpad.redhat.com/artifact-release-evidence/v1",
        "component": "serve",
        "source": {"repository": "https://example/repo", "revision": "d" * 40, "tree_dirty": False},
        "image": image,
        "architectures": ["amd64"],
        "build": {
            "builder_identity": "trusted-ci",
            "workflow_url": "https://example/run",
            "completed_at": "2026-09-21T00:00:00Z",
        },
        "checks": checks,
    }


def _source(tmp_path: Path, *, approved: bool = True, images: list[str] | None = None):
    policy = {
        "authority": {
            "origin": "quay.io/example",
            "state": "approved" if approved else "provisional",
            "organization_ownership_approved": approved,
        },
        "signing": {"identity_approved": approved},
        "repositories": {
            "serve": {"repository": "quay.io/example/serve", "pull_grant_verified": approved}
        },
        "retention": {"minimum_rollback_releases": 3},
    }
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy))
    release_dir = tmp_path / "releases" / "serve" / "v1"
    release_dir.mkdir(parents=True)
    receipt_bytes = yaml.safe_dump(_receipt()).encode()
    (release_dir / "receipt.yaml").write_bytes(receipt_bytes)
    manifest = {
        "schema_version": "launchpad.redhat.com/promoted-catalog-release/v1",
        "catalog_id": "serve",
        "catalog_release": "v1",
        "state": "promoted",
        "runtime_images_complete": True,
        "runtime_images": images if images is not None else [IMAGE],
        "image_evidence": [
            {
                "image": IMAGE,
                "path": "receipt.yaml",
                "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            }
        ],
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (release_dir / "release.json").write_bytes(raw)
    (release_dir / "release.sig").write_text(hmac.new(KEY, raw, hashlib.sha256).hexdigest())
    source = AuthenticatedPromotedReleaseSource(tmp_path / "releases", policy_path, KEY)
    return source, release_dir, policy_path


def test_signed_exact_release_resolves_all_immutable_images(tmp_path: Path):
    source, release_dir, _ = _source(tmp_path)
    release = source.get_promoted_release("serve", "v1")
    assert release.image_refs == [IMAGE]
    assert (
        release.promotion_evidence_id
        == "sha256:" + hashlib.sha256((release_dir / "release.json").read_bytes()).hexdigest()
    )
    assert source.get_promoted_release("serve", "v2") is None


def test_repository_policy_is_provisional_and_cannot_authorize_promotion(tmp_path: Path):
    _, release_dir, _ = _source(tmp_path)
    source = AuthenticatedPromotedReleaseSource(
        release_dir.parent.parent,
        ROOT / "config/artifact-registry-policy.yaml",
        KEY,
    )
    with pytest.raises(PromotedReleaseSourceError, match="ownership is not approved"):
        source.get_promoted_release("serve", "v1")


def test_invalid_key_and_release_path_are_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="signing key"):
        AuthenticatedPromotedReleaseSource(tmp_path, tmp_path / "policy.yaml", b"short")
    source, _, _ = _source(tmp_path)
    with pytest.raises(PromotedReleaseSourceError, match="identity"):
        source.get_promoted_release("../serve", "v1")


def test_catalog_path_component_symlink_is_rejected(tmp_path: Path):
    source, release_dir, _ = _source(tmp_path)
    catalog_dir = release_dir.parent
    relocated = tmp_path / "relocated-catalog"
    catalog_dir.rename(relocated)
    catalog_dir.symlink_to(relocated, target_is_directory=True)

    with pytest.raises(PromotedReleaseSourceError, match="symlink"):
        source.get_promoted_release("serve", "v1")


def test_release_root_symlink_is_rejected(tmp_path: Path):
    source, release_dir, _ = _source(tmp_path)
    root = release_dir.parent.parent
    relocated = tmp_path / "relocated-releases"
    root.rename(relocated)
    root.symlink_to(relocated, target_is_directory=True)

    with pytest.raises(PromotedReleaseSourceError, match="symlink"):
        source.get_promoted_release("serve", "v1")


@pytest.mark.parametrize(
    "change",
    [
        "unapproved",
        "tamper",
        "missing_signature",
        "extra_image",
        "mutable",
        "bad_receipt",
        "wrong_identity",
        "not_promoted",
        "path_escape",
        "duplicate_field",
    ],
)
def test_untrusted_or_incomplete_release_fails_closed(tmp_path: Path, change: str):
    source, release_dir, _ = _source(tmp_path, approved=change != "unapproved")
    manifest_path = release_dir / "release.json"
    if change == "tamper":
        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    elif change == "missing_signature":
        (release_dir / "release.sig").unlink()
    elif change in {"extra_image", "mutable", "wrong_identity", "not_promoted"}:
        manifest = json.loads(manifest_path.read_bytes())
        if change == "extra_image":
            manifest["runtime_images"].append("quay.io/example/other@sha256:" + "e" * 64)
        if change == "mutable":
            manifest["runtime_images"] = ["quay.io/example/serve:latest"]
        if change == "wrong_identity":
            manifest["catalog_release"] = "v2"
        if change == "not_promoted":
            manifest["state"] = "draft"
        raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        manifest_path.write_bytes(raw)
        (release_dir / "release.sig").write_text(hmac.new(KEY, raw, hashlib.sha256).hexdigest())
    elif change == "bad_receipt":
        (release_dir / "receipt.yaml").write_text("image: bad")
    elif change == "path_escape":
        manifest = json.loads(manifest_path.read_bytes())
        manifest["image_evidence"][0]["path"] = "../../other.yaml"
        raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        manifest_path.write_bytes(raw)
        (release_dir / "release.sig").write_text(hmac.new(KEY, raw, hashlib.sha256).hexdigest())
    elif change == "duplicate_field":
        raw = manifest_path.read_bytes().replace(
            b'"state":"promoted"', b'"state":"draft","state":"promoted"'
        )
        manifest_path.write_bytes(raw)
        (release_dir / "release.sig").write_text(hmac.new(KEY, raw, hashlib.sha256).hexdigest())
    with pytest.raises(PromotedReleaseSourceError):
        source.get_promoted_release("serve", "v1")
