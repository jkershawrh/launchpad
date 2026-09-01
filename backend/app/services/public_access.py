from __future__ import annotations

import hashlib
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.domain.access import (
    AccessPolicy,
    AccessSession,
    ClaimResult,
    EntitlementStatus,
    ParticipantEntitlement,
    ParticipantIdentity,
)


GENERIC_DENIAL = "Access request cannot be completed"


class PublicAccessService:
    """Passwordless, order-code access with atomic seat assignment.

    Email is deliberately unverified. The order code is the sole secret. The
    service stores only Argon2id code hashes and SHA-256 session-token hashes.
    """

    def __init__(
        self,
        public_domain: str | None = None,
        enabled: bool | None = None,
        store=None,
    ) -> None:
        self.public_domain = (public_domain or os.getenv("PUBLIC_LABS_DOMAIN", "")).strip(".")
        self.enabled = (
            enabled if enabled is not None
            else os.getenv("PUBLIC_ACCESS_ENABLED", "false").lower() == "true"
        )
        self.store = store
        self._hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
        self._policies: dict[str, AccessPolicy] = {}
        self._identities: dict[str, ParticipantIdentity] = {}
        self._entitlements: dict[tuple[str, str], ParticipantEntitlement] = {}
        self._sessions: dict[str, AccessSession] = {}
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self.audit_events: list[dict] = []
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self.store:
            return
        for policy in self.store.list_policies():
            self._policies[policy.order_id] = policy
        for identity in self.store.list_identities():
            self._identities[identity.normalized_email] = identity
        for entitlement in self.store.list_entitlements():
            self._entitlements[(entitlement.order_id, entitlement.participant_id)] = entitlement

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().casefold()

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:40] or "lab"

    @staticmethod
    def _new_code() -> str:
        raw = secrets.token_hex(10).upper()
        return "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_policy(
        self,
        *,
        order_id: str,
        order_type: str,
        catalog_slug: str,
        seat_refs: list[str],
        expires_at: datetime,
    ) -> tuple[AccessPolicy, str]:
        if not self.enabled or not self.public_domain:
            raise ValueError("Public access is not enabled")
        if not seat_refs:
            raise ValueError("Public access requires at least one seat")
        with self._lock:
            if order_id in self._policies:
                raise ValueError("Public access policy already exists")
            plaintext = self._new_code()
            short_id = re.sub(r"[^a-z0-9]", "", order_id.casefold())[:8]
            host = f"{self._slug(catalog_slug)}-{short_id}.{self.public_domain}"
            policy = AccessPolicy(
                order_id=order_id,
                order_type=order_type,
                catalog_slug=self._slug(catalog_slug),
                code_hash=self._hasher.hash(plaintext),
                seat_refs=seat_refs,
                public_url=f"https://{host}",
                expires_at=expires_at,
            )
            self._policies[order_id] = policy
            if self.store:
                self.store.save_policy(policy)
            return policy, plaintext

    def _rate_limit_keys(self, order_id: str, email: str, ip_address: str) -> tuple[str, str]:
        return f"ip:{order_id}:{ip_address}", f"email:{order_id}:{email}"

    def _check_rate_limit(self, order_id: str, email: str, ip_address: str) -> None:
        now = time.monotonic()
        for key in self._rate_limit_keys(order_id, email, ip_address):
            attempts = self._attempts[key]
            while attempts and now - attempts[0] > 900:
                attempts.popleft()
            if len(attempts) >= 5:
                raise ValueError(GENERIC_DENIAL)

    def _record_failure(self, order_id: str, email: str, ip_address: str) -> None:
        now = time.monotonic()
        for key in self._rate_limit_keys(order_id, email, ip_address):
            self._attempts[key].append(now)

    def _audit(self, event_type: str, order_id: str, outcome: str, participant_id: str = "") -> None:
        self.audit_events.append({
            "event_type": event_type,
            "order_id": order_id,
            "outcome": outcome,
            "participant_hash": hashlib.sha256(participant_id.encode()).hexdigest() if participant_id else None,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })

    def _verify(self, policy: AccessPolicy, code: str) -> bool:
        try:
            return self._hasher.verify(policy.code_hash, code)
        except (VerifyMismatchError, TypeError):
            return False

    def claim(self, order_id: str, email: str, code: str, ip_address: str) -> ClaimResult:
        normalized = self.normalize_email(email)
        self._check_rate_limit(order_id, normalized, ip_address)
        with self._lock:
            policy = self._policies.get(order_id)
            now = datetime.utcnow()
            if not policy or not policy.enabled or policy.expires_at <= now or not self._verify(policy, code):
                self._record_failure(order_id, normalized, ip_address)
                self._audit("claim", order_id, "denied")
                raise ValueError(GENERIC_DENIAL)

            identity = self._identities.get(normalized)
            if identity is None:
                participant_id = secrets.token_hex(16)
                identity = ParticipantIdentity(
                    participant_id=participant_id,
                    normalized_email=normalized,
                    keycloak_username=f"lp-{participant_id}",
                )
                self._identities[normalized] = identity
                if self.store:
                    self.store.save_identity(identity)

            key = (order_id, identity.participant_id)
            entitlement = self._entitlements.get(key)
            if entitlement:
                entitlement = entitlement.model_copy(update={
                    "status": EntitlementStatus.ACTIVE,
                    "code_version": policy.code_version,
                    "updated_at": now,
                })
            else:
                claimed = {
                    existing.seat_ref for existing in self._entitlements.values()
                    if existing.order_id == order_id and existing.status != EntitlementStatus.REVOKED
                }
                seat_ref = next((seat for seat in policy.seat_refs if seat not in claimed), None)
                if seat_ref is None:
                    raise ValueError(GENERIC_DENIAL)
                entitlement = ParticipantEntitlement(
                    participant_id=identity.participant_id,
                    order_id=order_id,
                    seat_ref=seat_ref,
                    code_version=policy.code_version,
                    expires_at=policy.expires_at,
                )
            self._entitlements[key] = entitlement
            if self.store:
                self.store.save_entitlement(entitlement)
            self._audit("claim", order_id, "granted", identity.participant_id)

            token = secrets.token_urlsafe(32)
            session = AccessSession(
                token_hash=self._token_hash(token),
                participant_id=identity.participant_id,
                expires_at=max(
                    item.expires_at for item in self._entitlements.values()
                    if item.participant_id == identity.participant_id
                    and item.status == EntitlementStatus.ACTIVE
                ),
            )
            self._sessions[session.token_hash] = session
            return ClaimResult(
                identity=identity,
                entitlement=entitlement,
                session_token=token,
                public_url=policy.public_url,
            )

    def validate_session(self, token: str, order_id: str) -> AccessSession:
        now = datetime.utcnow()
        session = self._sessions.get(self._token_hash(token))
        entitlement = self._entitlements.get((order_id, session.participant_id)) if session else None
        policy = self._policies.get(order_id)
        if (
            not session or session.revoked_at or session.expires_at <= now
            or not entitlement or entitlement.status != EntitlementStatus.ACTIVE
            or entitlement.expires_at <= now or not policy or not policy.enabled
            or entitlement.code_version != policy.code_version
        ):
            self._audit("authorize", order_id, "denied", session.participant_id if session else "")
            raise ValueError("Access denied")
        self._audit("authorize", order_id, "granted", session.participant_id)
        return session

    def rotate_code(self, order_id: str) -> str:
        with self._lock:
            policy = self._policies.get(order_id)
            if not policy:
                raise ValueError("Access policy not found")
            plaintext = self._new_code()
            policy = policy.model_copy(update={
                "code_hash": self._hasher.hash(plaintext),
                "code_version": policy.code_version + 1,
            })
            self._policies[order_id] = policy
            if self.store:
                self.store.save_policy(policy)
            for key, entitlement in list(self._entitlements.items()):
                if entitlement.order_id == order_id and entitlement.status == EntitlementStatus.ACTIVE:
                    updated = entitlement.model_copy(update={
                        "status": EntitlementStatus.REAUTH_REQUIRED,
                        "updated_at": datetime.utcnow(),
                    })
                    self._entitlements[key] = updated
                    if self.store:
                        self.store.save_entitlement(updated)
            self._audit("rotate", order_id, "completed")
            return plaintext

    def remove_participant(self, order_id: str, participant_id: str) -> None:
        with self._lock:
            entitlement = self._entitlements.get((order_id, participant_id))
            if not entitlement:
                raise ValueError("Participant entitlement not found")
            updated = entitlement.model_copy(update={
                "status": EntitlementStatus.REVOKED,
                "updated_at": datetime.utcnow(),
            })
            self._entitlements[(order_id, participant_id)] = updated
            if self.store:
                self.store.save_entitlement(updated)
            self._audit("participant_remove", order_id, "completed", participant_id)

    def expire_order(self, order_id: str) -> None:
        with self._lock:
            policy = self._policies.get(order_id)
            if policy:
                self._policies[order_id] = policy.model_copy(update={"enabled": False})
                if self.store:
                    self.store.save_policy(self._policies[order_id])
            for key, entitlement in list(self._entitlements.items()):
                if entitlement.order_id == order_id:
                    updated = entitlement.model_copy(update={
                        "status": EntitlementStatus.EXPIRED,
                        "updated_at": datetime.utcnow(),
                    })
                    self._entitlements[key] = updated
                    if self.store:
                        self.store.save_entitlement(updated)
            self._audit("expire", order_id, "completed")

    def entitlements_for(self, participant_id: str) -> list[ParticipantEntitlement]:
        return [item for item in self._entitlements.values() if item.participant_id == participant_id]

    def get_policy(self, order_id: str) -> AccessPolicy | None:
        return self._policies.get(order_id)
