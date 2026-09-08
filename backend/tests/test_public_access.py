from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.routers import public_access as public_access_router
from app.api.routers.public_access import _participant_tool_urls
from app.domain.access import EntitlementStatus, ExposurePolicy
from app.domain.clusters import ClusterTarget
from app.services.cluster_registry import ClusterRegistry
from app.services.public_access import PublicAccessService
from fastapi import HTTPException


def service():
    return PublicAccessService(public_domain="labs.example.io", enabled=True)


def test_public_gateway_receives_only_catalog_declared_tool_urls():
    session = SimpleNamespace(
        resources={
            "routes": {
                "mortgage-ai-ui-route": "https://mortgage-seat.apps.arena.example",
                "grafana-route": "https://grafana-seat.apps.arena.example",
                "undeclared-route": "https://undeclared.apps.arena.example",
            }
        }
    )
    catalog_item = SimpleNamespace(
        metadata={
            "showroom_tabs": [
                {"id": "mortgage-ai", "source": "workload.route.ui"},
                {"id": "grafana", "source": "workload.route.grafana"},
                {"id": "mlflow", "source": "cluster.mlflow_url"},
                {"id": "docs", "source": "https://docs.example.test"},
            ],
            "workload_routes": {
                "ui": "mortgage-ai-ui-route",
                "grafana": "grafana-route",
            },
        }
    )
    cluster = SimpleNamespace(service_urls={"mlflow": "https://mlflow.apps.arena.example"})

    assert _participant_tool_urls(session, catalog_item, cluster) == {
        "mortgage-ai": "https://mortgage-seat.apps.arena.example",
        "grafana": "https://grafana-seat.apps.arena.example",
        "mlflow": "https://mlflow.apps.arena.example",
    }


def test_public_gateway_includes_legacy_catalog_workspace_route():
    session = SimpleNamespace(
        resources={
            "routes": {
                "rag": "https://rag-seat.apps.arena.example",
                "undeclared-route": "https://undeclared.apps.arena.example",
            }
        }
    )
    catalog_item = SimpleNamespace(
        metadata={
            "workspace_route_name": "rag",
            "workspace_title": "RAG Assistant",
        }
    )

    assert _participant_tool_urls(session, catalog_item, None) == {
        "workspace": "https://rag-seat.apps.arena.example",
    }


def test_declared_workspace_tab_takes_precedence_over_legacy_workspace_route():
    session = SimpleNamespace(
        resources={
            "routes": {
                "multi-agent-ui": "https://multi-agent-seat.apps.arena.example",
            }
        }
    )
    catalog_item = SimpleNamespace(
        metadata={
            "workspace_route_name": "multi-agent-ui",
            "showroom_tabs": [
                {"id": "participant-ui", "source": "workload.route.ui"},
            ],
            "workload_routes": {"ui": "multi-agent-ui"},
        }
    )

    assert _participant_tool_urls(session, catalog_item, None) == {
        "participant-ui": "https://multi-agent-seat.apps.arena.example",
    }


def test_public_access_defaults_to_internal():
    assert ExposurePolicy.INTERNAL.value == "internal"


def test_code_is_one_time_plaintext_and_argon2id_hashed():
    access = service()
    policy, plaintext = access.create_policy(
        order_id="workshop-1",
        order_type="workshop",
        catalog_slug="operator-lab",
        seat_refs=["seat-1", "seat-2"],
        expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    assert plaintext not in policy.code_hash
    assert policy.code_hash.startswith("$argon2id$")
    assert len(plaintext.replace("-", "")) >= 16
    assert policy.public_url.startswith("https://operator-lab-")
    assert policy.public_url.endswith(".labs.example.io")


def test_claim_normalizes_email_and_recovers_same_seat():
    access = service()
    _, code = access.create_policy(
        order_id="workshop-12345678",
        order_type="workshop",
        catalog_slug="operator-lab",
        seat_refs=["seat-1", "seat-2"],
        expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    first = access.claim("workshop-12345678", " Person@Example.COM ", code, "192.0.2.1")
    recovered = access.claim("workshop-12345678", "person@example.com", code, "192.0.2.1")
    assert first.entitlement.seat_ref == "seat-1"
    assert recovered.entitlement.entitlement_id == first.entitlement.entitlement_id
    assert recovered.identity.normalized_email == "person@example.com"


def test_same_identity_can_claim_multiple_labs():
    access = service()
    _, code_a = access.create_policy(
        order_id="workshop-a",
        order_type="workshop",
        catalog_slug="lab-a",
        seat_refs=["a-1"],
        expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    _, code_b = access.create_policy(
        order_id="workshop-b",
        order_type="workshop",
        catalog_slug="lab-b",
        seat_refs=["b-1"],
        expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    a = access.claim("workshop-a", "person@example.com", code_a, "192.0.2.1")
    b = access.claim("workshop-b", "person@example.com", code_b, "192.0.2.1")
    assert a.identity.participant_id == b.identity.participant_id
    assert {e.order_id for e in access.entitlements_for(a.identity.participant_id)} == {
        "workshop-a",
        "workshop-b",
    }


def test_concurrent_claims_never_duplicate_a_seat():
    access = service()
    _, code = access.create_policy(
        order_id="burst-order",
        order_type="workshop",
        catalog_slug="burst",
        seat_refs=[f"seat-{i}" for i in range(1, 26)],
        expires_at=datetime.utcnow() + timedelta(hours=4),
    )
    with ThreadPoolExecutor(max_workers=25) as pool:
        claims = list(
            pool.map(
                lambda i: access.claim(
                    "burst-order", f"user-{i}@example.com", code, f"192.0.2.{i}"
                ),
                range(1, 26),
            )
        )
    assert len({claim.entitlement.seat_ref for claim in claims}) == 25


def test_full_order_rejects_without_leaking_participants():
    access = service()
    _, code = access.create_policy(
        order_id="full",
        order_type="individual",
        catalog_slug="lab",
        seat_refs=["only"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    access.claim("full", "first@example.com", code, "192.0.2.1")
    with pytest.raises(ValueError, match="Access request cannot be completed"):
        access.claim("full", "second@example.com", code, "192.0.2.2")


def test_rotation_requires_reauthentication_and_new_code_restores_seat():
    access = service()
    _, code = access.create_policy(
        order_id="rotate",
        order_type="workshop",
        catalog_slug="lab",
        seat_refs=["seat-1"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
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
        order_id="expired",
        order_type="individual",
        catalog_slug="lab",
        seat_refs=["seat"],
        expires_at=datetime.utcnow() + timedelta(seconds=1),
    )
    claim = access.claim("expired", "person@example.com", code, "192.0.2.1")
    access.expire_order("expired")
    with pytest.raises(ValueError, match="Access denied"):
        access.validate_session(claim.session_token, "expired")


def test_shared_pilot_host_selects_only_current_active_policy():
    access = service()
    old, _ = access.create_policy(
        order_id="old",
        order_type="individual",
        catalog_slug="lab",
        seat_refs=["old-seat"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    access._policies["old"] = old.model_copy(update={"public_url": "https://pilot.example.io"})
    access.expire_order("old")
    current, _ = access.create_policy(
        order_id="current",
        order_type="individual",
        catalog_slug="lab",
        seat_refs=["current-seat"],
        expires_at=datetime.utcnow() + timedelta(hours=2),
    )
    access._policies["current"] = current.model_copy(
        update={"public_url": "https://pilot.example.io"}
    )
    assert access.get_policy_by_host("pilot.example.io").order_id == "current"


def test_shared_pilot_origin_is_used_without_creating_unroutable_subdomains():
    access = PublicAccessService(
        enabled=True,
        shared_origin="https://public-pilot.trycloudflare.com",
    )

    policy, _ = access.create_policy(
        order_id="shared-pilot",
        order_type="workshop",
        catalog_slug="operators",
        seat_refs=["seat-1"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )

    assert policy.public_url == "https://public-pilot.trycloudflare.com"


def test_shared_pilot_origin_rejects_a_second_active_order():
    access = PublicAccessService(
        enabled=True,
        shared_origin="https://public-pilot.trycloudflare.com",
    )
    access.create_policy(
        order_id="first-pilot",
        order_type="workshop",
        catalog_slug="operators",
        seat_refs=["seat-1", "seat-2"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="already has an active order"):
        access.create_policy(
            order_id="second-pilot",
            order_type="individual",
            catalog_slug="operators",
            seat_refs=["seat-3"],
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )


def test_public_placement_requires_public_enabled_cluster():
    registry = ClusterRegistry(
        [
            ClusterTarget(
                cluster_id="private",
                display_name="Private",
                ingress_domain="apps.private",
                capabilities=["openshift"],
            ),
            ClusterTarget(
                cluster_id="public",
                display_name="Public",
                ingress_domain="apps.public",
                capabilities=["openshift"],
                public_access_enabled=True,
                public_ingress_domain="labs.example.io",
            ),
        ]
    )
    assert registry.select(["openshift"], require_public_access=True).cluster_id == "public"


def test_arena_pilot_flag_does_not_make_any_other_cluster_public(monkeypatch):
    registry = ClusterRegistry(
        [
            ClusterTarget(
                cluster_id="arena",
                display_name="Arena",
                ingress_domain="apps.arena.example",
                capabilities=["openshift"],
            ),
            ClusterTarget(
                cluster_id="other",
                display_name="Other",
                ingress_domain="apps.other.example",
                capabilities=["openshift"],
            ),
        ]
    )
    monkeypatch.setenv("PUBLIC_ACCESS_PILOT_CLUSTER", "arena")

    eligible = registry.eligible(["openshift"], require_public_access=True)

    assert [target.cluster_id for target in eligible] == ["arena"]


def test_only_failed_claims_consume_rate_limit_budget():
    access = service()
    _, code = access.create_policy(
        order_id="order-rate",
        order_type="individual",
        catalog_slug="sandbox",
        seat_refs=["seat"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    for _ in range(8):
        assert (
            access.claim("order-rate", "same@example.com", code, "192.0.2.10").entitlement.seat_ref
            == "seat"
        )


def test_participant_removal_reopens_the_seat():
    access = service()
    _, code = access.create_policy(
        order_id="order-remove",
        order_type="workshop",
        catalog_slug="operators",
        seat_refs=["seat"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    first = access.claim("order-remove", "first@example.com", code, "192.0.2.11")
    access.remove_participant("order-remove", first.identity.participant_id)
    assert (
        access.claim("order-remove", "second@example.com", code, "192.0.2.12").entitlement.seat_ref
        == "seat"
    )


def test_owner_summary_counts_only_active_claims(monkeypatch):
    policy = SimpleNamespace(
        order_id="order-summary",
        public_url="https://lab.example.io",
        enabled=True,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        seat_limit=2,
        code_version=1,
    )
    fake_service = SimpleNamespace(
        get_policy=lambda order_id: policy,
        _entitlements={
            "active": SimpleNamespace(order_id="order-summary", status=EntitlementStatus.ACTIVE),
            "revoked": SimpleNamespace(order_id="order-summary", status=EntitlementStatus.REVOKED),
        },
    )
    monkeypatch.setattr(public_access_router, "public_access_service", fake_service)

    assert public_access_router._owner_summary("order-summary")["claim_count"] == 1


def test_keycloak_validation_fails_closed_when_namespace_binding_fails(monkeypatch):
    access = service()
    _, code = access.create_policy(
        order_id="binding-failure",
        order_type="workshop",
        catalog_slug="operators",
        seat_refs=["seat-1"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )

    class RejectBinding:
        @staticmethod
        def bind_public_participant(*_args):
            raise RuntimeError("Arena rejected the RoleBinding")

    monkeypatch.setenv("ACCESS_BROKER_KEY", "test-broker-key")
    monkeypatch.setattr(public_access_router, "public_access_service", access)
    monkeypatch.setattr(public_access_router, "provisioning_service", RejectBinding())

    with pytest.raises(HTTPException) as exc:
        public_access_router.keycloak_validate(
            public_access_router.ClaimRequest(
                order_id="binding-failure",
                email="first@example.com",
                code=code,
            ),
            SimpleNamespace(client=SimpleNamespace(host="192.0.2.40")),
            "test-broker-key",
        )

    assert exc.value.status_code == 503
    assert not [
        entitlement
        for entitlement in access._entitlements.values()
        if entitlement.order_id == "binding-failure"
        and entitlement.status == EntitlementStatus.ACTIVE
    ]
    assert (
        access.claim(
            "binding-failure", "second@example.com", code, "192.0.2.41"
        ).entitlement.seat_ref
        == "seat-1"
    )


def test_keycloak_can_recover_order_from_unique_active_code(monkeypatch):
    access = service()
    _, code = access.create_policy(
        order_id="console-sso",
        order_type="workshop",
        catalog_slug="operators",
        seat_refs=["seat-1"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    bindings = []

    class RecordBinding:
        @staticmethod
        def bind_public_participant(order_id, seat_ref, username):
            bindings.append((order_id, seat_ref, username))

    monkeypatch.setenv("ACCESS_BROKER_KEY", "test-broker-key")
    monkeypatch.setattr(public_access_router, "public_access_service", access)
    monkeypatch.setattr(public_access_router, "provisioning_service", RecordBinding())

    result = public_access_router.keycloak_validate_by_code(
        public_access_router.CodeClaimRequest(
            email="participant@example.com",
            code=code,
        ),
        SimpleNamespace(client=SimpleNamespace(host="192.0.2.42")),
        "test-broker-key",
    )

    assert result["active"] is True
    assert result["order_id"] == "console-sso"
    assert result["seat_ref"] == "seat-1"
    assert bindings == [("console-sso", "seat-1", result["preferred_username"])]


def test_admin_can_change_only_the_https_origin_for_a_pilot_order():
    access = service()
    access.create_policy(
        order_id="pilot-url",
        order_type="workshop",
        catalog_slug="operators",
        seat_refs=["seat-1"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )

    updated = access.set_public_url("pilot-url", "https://public-pilot.trycloudflare.com")

    assert updated.public_url == "https://public-pilot.trycloudflare.com"
    assert access.get_policy_by_host("public-pilot.trycloudflare.com").order_id == "pilot-url"
    for invalid in (
        "http://public-pilot.trycloudflare.com",
        "https://user:secret@public-pilot.trycloudflare.com",
        "https://public-pilot.trycloudflare.com/another-app",
    ):
        with pytest.raises(ValueError, match="HTTPS origin"):
            access.set_public_url("pilot-url", invalid)

    access.create_policy(
        order_id="second-pilot-url",
        order_type="individual",
        catalog_slug="operators",
        seat_refs=["seat-2"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    with pytest.raises(ValueError, match="already belongs to an active order"):
        access.set_public_url("second-pilot-url", "https://public-pilot.trycloudflare.com")


def test_public_access_never_uses_placeholder_workspace_url():
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "app/api/routers/public_access.py"
    ).read_text()
    assert '"example.com" in workspace_url' in source
    assert '".apps.cluster.local" in workspace_url' in source
    assert "/k8s/ns/" in source
    assert "/core~v1~Pod" in source


def test_public_access_never_falls_back_to_private_console_url():
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "app/api/routers/public_access.py"
    ).read_text()
    assert "public_console_url or target.console_url" not in source
    assert "public_console_url or cluster.console_url" not in source
    assert "console_url = target.public_console_url" in source
    assert "console_url = cluster.public_console_url" in source


def test_backend_restart_recovers_policy_identity_entitlement_and_session():
    class Store:
        def __init__(self):
            self.policies = {}
            self.identities = {}
            self.entitlements = {}
            self.sessions = {}

        def save_policy(self, value):
            self.policies[value.order_id] = value

        def save_identity(self, value):
            self.identities[value.participant_id] = value

        def save_entitlement(self, value):
            self.entitlements[value.entitlement_id] = value

        def save_session(self, value):
            self.sessions[value.session_id] = value

        def list_policies(self):
            return list(self.policies.values())

        def list_identities(self):
            return list(self.identities.values())

        def list_entitlements(self):
            return list(self.entitlements.values())

        def list_sessions(self):
            return list(self.sessions.values())

    store = Store()
    first = PublicAccessService(public_domain="labs.example.io", enabled=True, store=store)
    _, code = first.create_policy(
        order_id="restart",
        order_type="individual",
        catalog_slug="sandbox",
        seat_refs=["seat"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    claim = first.claim("restart", "person@example.com", code, "192.0.2.20")
    restarted = PublicAccessService(public_domain="labs.example.io", enabled=True, store=store)
    assert (
        restarted.validate_session(claim.session_token, "restart").participant_id
        == claim.identity.participant_id
    )


def test_final_entitlement_expiry_disables_identity_and_revokes_session():
    access = service()
    _, code = access.create_policy(
        order_id="final",
        order_type="individual",
        catalog_slug="sandbox",
        seat_refs=["seat"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    claim = access.claim("final", "person@example.com", code, "192.0.2.21")
    access.expire_order("final")
    identity = access._identities["person@example.com"]
    assert identity.disabled_at is not None
    assert access._sessions[access._token_hash(claim.session_token)].revoked_at is not None


def test_claiming_a_later_lab_reactivates_the_ephemeral_identity():
    access = service()
    _, first_code = access.create_policy(
        order_id="first",
        order_type="individual",
        catalog_slug="sandbox",
        seat_refs=["first-seat"],
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    first = access.claim("first", "person@example.com", first_code, "192.0.2.30")
    access.expire_order("first")
    assert access._identities["person@example.com"].disabled_at is not None
    _, next_code = access.create_policy(
        order_id="next",
        order_type="individual",
        catalog_slug="operators",
        seat_refs=["next-seat"],
        expires_at=datetime.utcnow() + timedelta(hours=2),
    )
    resumed = access.claim("next", "person@example.com", next_code, "192.0.2.30")
    assert resumed.identity.participant_id == first.identity.participant_id
    assert resumed.identity.disabled_at is None
