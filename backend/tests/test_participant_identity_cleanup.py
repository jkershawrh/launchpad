import pytest
from app.services.participant_identity_cleanup import (
    DisabledIdentityCleanupCoordinator,
    ParticipantIdentityCleanupService,
)


class FakeKeycloak:
    def __init__(self) -> None:
        self.usernames: list[str] = []

    def disable_and_logout(self, username: str) -> bool:
        self.usernames.append(username)
        return True


class FakeOpenShift:
    def __init__(self) -> None:
        self.usernames: list[str] = []

    def revoke_tokens_and_user(self, username: str) -> tuple[int, bool]:
        self.usernames.append(username)
        return 2, True


def test_cleanup_disables_keycloak_before_revoking_openshift_identity() -> None:
    keycloak = FakeKeycloak()
    openshift = FakeOpenShift()
    service = ParticipantIdentityCleanupService(keycloak, openshift)

    result = service.cleanup("lp-a1b2c3")

    assert keycloak.usernames == ["lp-a1b2c3"]
    assert openshift.usernames == ["lp-a1b2c3"]
    assert result.keycloak_disabled is True
    assert result.openshift_tokens_revoked == 2
    assert result.openshift_user_removed is True


@pytest.mark.parametrize(
    "username",
    ["kubeadmin", "system:admin", "lp-", "lp-UPPER", "lp-safe/../../admin"],
)
def test_cleanup_rejects_every_non_participant_username(username: str) -> None:
    service = ParticipantIdentityCleanupService(FakeKeycloak(), FakeOpenShift())

    with pytest.raises(ValueError, match="participant|valid"):
        service.cleanup(username)


def test_coordinator_rechecks_durable_state_before_each_cleanup() -> None:
    keycloak = FakeKeycloak()
    openshift = FakeOpenShift()
    service = ParticipantIdentityCleanupService(keycloak, openshift)
    cleaned: list[str] = []

    def guarded(username, operation):
        if username == "lp-active-again":
            return None
        cleaned.append(username)
        return operation(username)

    results = DisabledIdentityCleanupCoordinator(
        lambda: ["lp-disabled", "lp-active-again", "lp-disabled"],
        guarded,
        service,
    ).run()

    assert cleaned == ["lp-disabled"]
    assert [item.username for item in results] == ["lp-disabled"]
