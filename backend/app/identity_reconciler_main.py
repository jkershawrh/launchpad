from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime

from app.adapters.openshift.participant_identity_cleanup import (
    KeycloakParticipantIdentityAdapter,
    OpenShiftParticipantIdentityAdapter,
)
from app.services.participant_identity_cleanup import (
    DisabledIdentityCleanupCoordinator,
    ParticipantIdentityCleanupService,
)
from app.storage.database import get_database_url

logger = logging.getLogger("launchpad.identity-reconciler")


class PostgresDisabledIdentitySource:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg2

        return psycopg2.connect(self.database_url, connect_timeout=5)

    def candidate_usernames(self) -> list[str]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT data->>'keycloak_username'
                       FROM participant_identities
                       WHERE data->>'disabled_at' IS NOT NULL
                         AND data->>'keycloak_username' LIKE 'lp-%'"""
                )
                return [str(row[0]) for row in cursor.fetchall()]
        finally:
            connection.close()

    def cleanup_if_still_disabled(
        self,
        username: str,
        cleanup: Callable[[str], object],
    ) -> object | None:
        connection = self._connect()
        try:
            connection.set_session(isolation_level="READ COMMITTED")
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT data
                       FROM participant_identities
                       WHERE data->>'keycloak_username' = %s""",
                    (username,),
                )
                row = cursor.fetchone()
                if not row:
                    connection.rollback()
                    return None
                identity = row[0]
                if isinstance(identity, str):
                    import json

                    identity = json.loads(identity)
                normalized_email = str(identity["normalized_email"])
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"access-email:{normalized_email}",),
                )
                cursor.execute(
                    """SELECT data
                       FROM participant_identities
                       WHERE data->>'keycloak_username' = %s
                       FOR UPDATE""",
                    (username,),
                )
                locked = cursor.fetchone()
                if not locked:
                    connection.rollback()
                    return None
                current = locked[0]
                if isinstance(current, str):
                    import json

                    current = json.loads(current)
                if not current.get("disabled_at"):
                    connection.rollback()
                    return None
                cursor.execute(
                    """SELECT COUNT(*)
                       FROM participant_entitlements
                       WHERE data->>'participant_id' = %s
                         AND data->>'status' IN ('active', 'reauth_required')
                         AND (data->>'expires_at')::timestamptz > %s""",
                    (current["participant_id"], datetime.now(UTC)),
                )
                if int(cursor.fetchone()[0]) != 0:
                    connection.rollback()
                    return None
                result = cleanup(username)
                connection.commit()
                return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    database_url = get_database_url()
    if not database_url:
        logger.error("DATABASE_URL is required")
        return 2
    source = PostgresDisabledIdentitySource(database_url)
    cleanup_service = ParticipantIdentityCleanupService(
        KeycloakParticipantIdentityAdapter(
            base_url=required("KEYCLOAK_ADMIN_BASE_URL"),
            realm=os.environ.get("KEYCLOAK_REALM", "launchpad-public"),
            client_id=required("KEYCLOAK_RECONCILER_CLIENT_ID"),
            client_secret=required("KEYCLOAK_RECONCILER_CLIENT_SECRET"),
        ),
        OpenShiftParticipantIdentityAdapter(),
    )
    results = DisabledIdentityCleanupCoordinator(
        source.candidate_usernames,
        source.cleanup_if_still_disabled,
        cleanup_service,
    ).run()
    logger.info(
        "Reconciled %d disabled participant identities; revoked %d OpenShift tokens",
        len(results),
        sum(item.openshift_tokens_revoked for item in results),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
