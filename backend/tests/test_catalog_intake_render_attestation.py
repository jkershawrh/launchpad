from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from app.services.catalog_intake_render_attestation import (
    SCHEMA,
    canonical_render_attestation_payload,
    verify_render_attestation,
)

SECRET = b"local-test-render-key-not-for-production"


def _expected() -> dict[str, str]:
    return {
        "catalog_item_id": "support-assistant",
        "source_revision": "a" * 40,
        "helm_values_sha256": "sha256:" + "b" * 64,
        "manifest_sha256": "sha256:" + "c" * 64,
        "renderer_image_digest": "sha256:" + "d" * 64,
        "render_review_sha256": "sha256:" + "e" * 64,
    }


def _envelope(*, secret: bytes = SECRET) -> dict:
    envelope = {
        "schema_version": SCHEMA,
        "producer_id": "catalog-renderer-ci",
        "observed_at": datetime(2026, 9, 22, 18, tzinfo=UTC).isoformat(),
        **_expected(),
        "network_egress_denied": True,
        "workspace_removed": True,
    }
    envelope["mac"] = hmac.new(
        secret,
        canonical_render_attestation_payload(envelope),
        hashlib.sha256,
    ).hexdigest()
    return envelope


def _verify(envelope: dict, **kwargs: object) -> dict:
    return verify_render_attestation(
        envelope,
        expected=_expected(),
        trusted_producers={"catalog-renderer-ci": SECRET},
        **kwargs,
    )


def test_authenticated_render_attestation_binds_exact_review() -> None:
    result = _verify(_envelope())

    assert result == {
        "schema_version": "launchpad.redhat.com/catalog-intake-render-attestation-status/v1",
        "status": "GREEN-local-authenticated",
        "authenticated": True,
        "producer_id": "catalog-renderer-ci",
        "catalog_item_id": "support-assistant",
        "source_revision": "a" * 40,
        "render_review_sha256": "sha256:" + "e" * 64,
        "findings": [],
        "release_eligible": False,
    }


def test_tampered_binding_or_mac_fails_closed() -> None:
    tampered = _envelope()
    tampered["manifest_sha256"] = "sha256:" + "f" * 64
    assert "attestation-mac-invalid" in _verify(tampered)["findings"]

    wrong_key = verify_render_attestation(
        _envelope(),
        expected=_expected(),
        trusted_producers={"catalog-renderer-ci": b"different-test-key-material"},
    )
    assert wrong_key["authenticated"] is False
    assert "attestation-mac-invalid" in wrong_key["findings"]


def test_unknown_or_weak_producer_key_fails_closed() -> None:
    assert (
        "trusted-producer-unavailable"
        in verify_render_attestation(_envelope(), expected=_expected(), trusted_producers={})[
            "findings"
        ]
    )
    assert (
        "trusted-producer-unavailable"
        in verify_render_attestation(
            _envelope(),
            expected=_expected(),
            trusted_producers={"catalog-renderer-ci": b"short"},
        )["findings"]
    )


def test_attestation_requires_exact_fields_and_expected_bindings() -> None:
    extra = _envelope()
    extra["untrusted"] = "ignored-if-not-rejected"
    assert "attestation-fields-invalid" in _verify(extra)["findings"]

    missing = _envelope()
    del missing["workspace_removed"]
    assert "attestation-fields-invalid" in _verify(missing)["findings"]

    expected = _expected()
    expected["source_revision"] = "f" * 40
    result = verify_render_attestation(
        _envelope(),
        expected=expected,
        trusted_producers={"catalog-renderer-ci": SECRET},
    )
    assert "attestation-binding-mismatch" in result["findings"]


def test_unproven_isolation_or_invalid_time_fails_closed() -> None:
    isolation = _envelope()
    isolation["network_egress_denied"] = False
    isolation["mac"] = hmac.new(
        SECRET,
        canonical_render_attestation_payload(isolation),
        hashlib.sha256,
    ).hexdigest()
    assert "render-isolation-unverified" in _verify(isolation)["findings"]

    observed = _envelope()
    observed["observed_at"] = "2026-09-22T18:00:00"
    observed["mac"] = hmac.new(
        SECRET,
        canonical_render_attestation_payload(observed),
        hashlib.sha256,
    ).hexdigest()
    assert "attestation-time-invalid" in _verify(observed)["findings"]


def test_findings_never_echo_secret_or_unknown_values() -> None:
    marker = "do-not-echo-this-key"
    envelope = _envelope()
    envelope["producer_id"] = marker
    result = verify_render_attestation(
        envelope,
        expected=_expected(),
        trusted_producers={marker: SECRET},
    )

    assert marker not in str(result["findings"])
    assert SECRET.decode() not in str(result)
