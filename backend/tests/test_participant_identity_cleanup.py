import pytest
from app.identity_reconciler_main import PostgresDisabledIdentitySource
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


class FakeCursor:
    def __init__(self, rows) -> None:
        self.rows = iter(rows)
        self.statements: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, params=None) -> None:
        self.statements.append((" ".join(statement.split()), params))

    def fetchone(self):
        return next(self.rows)

    def fetchall(self):
        return next(self.rows)


class FakeConnection:
    def __init__(self, rows) -> None:
        self.cursor_instance = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def set_session(self, **_kwargs) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None


def test_cleanup_source_skips_identities_already_reconciled(monkeypatch) -> None:
    connection = FakeConnection([[('lp-disabled',)]])
    source = PostgresDisabledIdentitySource("postgresql://unused")
    monkeypatch.setattr(source, "_connect", lambda: connection)

    assert source.candidate_usernames() == ["lp-disabled"]
    statement = connection.cursor_instance.statements[0][0]
    assert "data->>'external_cleanup_at' IS NULL" in statement


def test_successful_cleanup_is_marked_durably(monkeypatch) -> None:
    identity = {
        "participant_id": "participant-1",
        "normalized_email": "person@example.com",
        "keycloak_username": "lp-disabled",
        "disabled_at": "2026-10-06T12:00:00Z",
    }
    connection = FakeConnection([(identity,), (identity,), (0,)])
    source = PostgresDisabledIdentitySource("postgresql://unused")
    monkeypatch.setattr(source, "_connect", lambda: connection)

    result = source.cleanup_if_still_disabled("lp-disabled", lambda username: username)

    assert result == "lp-disabled"
    assert connection.commits == 1
    update = next(
        statement
        for statement, _params in connection.cursor_instance.statements
        if statement.startswith("UPDATE participant_identities")
    )
    assert "external_cleanup_at" in update
