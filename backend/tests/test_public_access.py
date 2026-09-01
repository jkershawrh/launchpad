from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from app.domain.access import EntitlementStatus, ExposurePolicy
from app.domain.clusters import ClusterTarget
from app.services.cluster_registry import ClusterRegistry
from app.services.public_access import PublicAccessService


def service():
    return PublicAccessService(public_domain="labs.example.io", enabled=True)


def test_public_access_defaults_to_internal():
    assert ExposurePolicy.INTERNAL.value == "internal"


def test_code_is_one_time_plaintext_and_argon2id_hashed():
    access = service()
    policy, plaintext = access.create_policy(
        order_id="workshop-1", order_type="workshop", catalog_slug="operator-lab",
        seat_refs=["seat-1", "seat-2"], expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    assert plaintext not in policy.code_hash
    assert policy.code_hash.startswith("$argon2id$")
    assert len(plaintext.replace("-", "")) >= 16
    assert policy.public_url.startswith("https://operator-lab-")
    assert policy.public_url.endswith(".labs.example.io")


def test_claim_normalizes_email_and_recovers_same_seat():
    access = service()
    _, code = access.create_policy(
        order_id="workshop-12345678", order_type="workshop", catalog_slug="operator-lab",
        seat_refs=["seat-1", "seat-2"], expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    first = access.claim("workshop-12345678", " Person@Example.COM ", code, "192.0.2.1")
    recovered = access.claim("workshop-12345678", "person@example.com", code, "192.0.2.1")
    assert first.entitlement.seat_ref == "seat-1"
    assert recovered.entitlement.entitlement_id == first.entitlement.entitlement_id
    assert recovered.identity.normalized_email == "person@example.com"


def test_same_identity_can_claim_multiple_labs():
    access = service()
    _, code_a = access.create_policy(
        order_id="workshop-a", order_type="workshop", catalog_slug="lab-a",
        seat_refs=["a-1"], expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    _, code_b = access.create_policy(
        order_id="workshop-b", order_type="workshop", catalog_slug="lab-b",
        seat_refs=["b-1"], expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    a = access.claim("workshop-a", "person@example.com", code_a, "192.0.2.1")
    b = access.claim("workshop-b", "person@example.com", code_b, "192.0.2.1")
    assert a.identity.participant_id == b.identity.participant_id
    assert {e.order_id for e in access.entitlements_for(a.identity.participant_id)} == {"workshop-a", "workshop-b"}


def test_concurrent_claims_never_duplicate_a_seat():
    access = service()
    _, code = access.create_policy(
        order_id="burst-order", order_type="workshop", catalog_slug="burst",
        seat_refs=[f"seat-{i}" for i in range(1, 26)], expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    with ThreadPoolExecutor(max_workers=25) as pool:
        claims = list(pool.map(
            lambda i: access.claim("burst-order", f"user-{i}@example.com", code, f"192.0.2.{i}"),
            range(1, 26),
        ))
    assert len({claim.entitlement.seat_ref for claim in claims}) == 25


def test_full_order_rejects_without_leaking_participants():
    access = service()
    _, code = access.create_policy(
        order_id="full", order_type="individual", catalog_slug="lab",
        seat_refs=["only"], expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    access.claim("full", "first@example.com", code, "192.0.2.1")
    with pytest.raises(ValueError, match="Access request cannot be completed"):
        access.claim("full", "second@example.com", code, "192.0.2.2")


def test_rotation_requires_reauthentication_and_new_code_restores_seat():
    access = service()
    _, code = access.create_policy(
        order_id="rotate", order_type="workshop", catalog_slug="lab",
        seat_refs=["seat-1"], expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    claim = access.claim("rotate", "person@example.com", code, "192.0.2.1")
    session = access.validate_session(claim.session_token, "rotate")
    assert session.participant_id == claim.identity.participant_id
    new_code = access.rotate_code("rotate")
    with pytest.raises(ValueError, match="Access denied"):
        access.validate_session(claim.session_token, "rotate")
    restored = access.claim("rotate", "person@example.com", new_code, "192.0.2.1")
    assert restored.entitlement.seat_ref == "seat-1"
    assert restored.entitlement.status == EntitlementStatus.ACTIVE


def test_expired_policy_denies_claim_and_session():
    access = service()
    _, code = access.create_policy(
        order_id="expired", order_type="individual", catalog_slug="lab",
        seat_refs=["seat"], expires_at=datetime.utcnow() + timedelta(seconds=1),
    )
    claim = access.claim("expired", "person@example.com", code, "192.0.2.1")
    access.expire_order("expired")
    with pytest.raises(ValueError, match="Access denied"):
        access.validate_session(claim.session_token, "expired")


def test_public_placement_requires_public_enabled_cluster():
    registry = ClusterRegistry([
        ClusterTarget(cluster_id="private", display_name="Private", ingress_domain="apps.private", capabilities=["openshift"]),
        ClusterTarget(cluster_id="public", display_name="Public", ingress_domain="apps.public", capabilities=["openshift"], public_access_enabled=True, public_ingress_domain="labs.example.io"),
    ])
    assert registry.select(["openshift"], require_public_access=True).cluster_id == "public"


def test_only_failed_claims_consume_rate_limit_budget():
    access = service()
    _, code = access.create_policy(
        order_id="order-rate", order_type="individual", catalog_slug="sandbox",
        seat_refs=["seat"], expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    for _ in range(8):
        assert access.claim("order-rate", "same@example.com", code, "192.0.2.10").entitlement.seat_ref == "seat"


def test_participant_removal_reopens_the_seat():
    access = service()
    _, code = access.create_policy(
        order_id="order-remove", order_type="workshop", catalog_slug="operators",
        seat_refs=["seat"], expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    first = access.claim("order-remove", "first@example.com", code, "192.0.2.11")
    access.remove_participant("order-remove", first.identity.participant_id)
    assert access.claim("order-remove", "second@example.com", code, "192.0.2.12").entitlement.seat_ref == "seat"
