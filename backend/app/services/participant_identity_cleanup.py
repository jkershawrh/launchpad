from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class ParticipantIdentityProvider(Protocol):
    def disable_and_logout(self, username: str) -> bool: ...


class OpenShiftIdentityProvider(Protocol):
    def revoke_tokens_and_user(self, username: str) -> tuple[int, bool]: ...


@dataclass(frozen=True)
class IdentityCleanupResult:
    username: str
    keycloak_disabled: bool
    openshift_tokens_revoked: int
    openshift_user_removed: bool


class ParticipantIdentityCleanupService:
    """Remove external identity state after Launchpad access ends.

    The caller must hold the durable participant identity lock while invoking
    this service.  That prevents a valid new claim from racing with cleanup.
    """

    def __init__(
        self,
        keycloak: ParticipantIdentityProvider,
        openshift: OpenShiftIdentityProvider,
    ) -> None:
        self.keycloak = keycloak
        self.openshift = openshift

    @staticmethod
    def _validate_username(username: str) -> str:
        if not username.startswith("lp-") or len(username) <= 3:
            raise ValueError("Only Launchpad participant identities can be cleaned")
        if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in username):
            raise ValueError("Participant username is not valid")
        return username

    def cleanup(self, username: str) -> IdentityCleanupResult:
        username = self._validate_username(username)
        keycloak_disabled = self.keycloak.disable_and_logout(username)
        tokens_revoked, user_removed = self.openshift.revoke_tokens_and_user(username)
        return IdentityCleanupResult(
            username=username,
            keycloak_disabled=keycloak_disabled,
            openshift_tokens_revoked=tokens_revoked,
            openshift_user_removed=user_removed,
        )


class DisabledIdentityCleanupCoordinator:
    """Coordinate durable eligibility checks with external cleanup."""

    def __init__(
        self,
        candidate_usernames: Callable[[], list[str]],
        cleanup_if_still_disabled: Callable[[str, Callable[[str], object]], object | None],
        cleanup_service: ParticipantIdentityCleanupService,
    ) -> None:
        self.candidate_usernames = candidate_usernames
        self.cleanup_if_still_disabled = cleanup_if_still_disabled
        self.cleanup_service = cleanup_service

    def run(self) -> list[IdentityCleanupResult]:
        results: list[IdentityCleanupResult] = []
        for username in sorted(set(self.candidate_usernames())):
            result = self.cleanup_if_still_disabled(
                username,
                self.cleanup_service.cleanup,
            )
            if isinstance(result, IdentityCleanupResult):
                results.append(result)
        return results


def active_entitlement_at(expires_at: datetime, status: str, *, now: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return status in {"active", "reauth_required"} and expires_at > now
