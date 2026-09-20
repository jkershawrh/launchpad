from __future__ import annotations

import hashlib
import json
import logging
from threading import RLock
from typing import Protocol

from app.domain.catalog_intake import CatalogIntakeDraft
from app.storage.database import get_database_url
from app.storage.stores import PersistenceUnavailableError

logger = logging.getLogger("launchpad.catalog-intakes")


class CatalogIntakeDraftConflictError(ValueError):
    """An existing content identity was presented with different draft data."""


class CatalogIntakeDraftStore(Protocol):
    durable: bool

    def create_idempotent(self, draft: CatalogIntakeDraft) -> CatalogIntakeDraft: ...

    def get(self, intake_id: str) -> CatalogIntakeDraft | None: ...

    def list_all(self) -> list[CatalogIntakeDraft]: ...


def _serialized(draft: CatalogIntakeDraft) -> str:
    return json.dumps(
        draft.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def _fingerprint(draft: CatalogIntakeDraft) -> str:
    return hashlib.sha256(_serialized(draft).encode()).hexdigest()


def _decoded(value):
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


class InMemoryCatalogIntakeDraftStore:
    durable = False

    def __init__(self) -> None:
        self._drafts: dict[str, CatalogIntakeDraft] = {}
        self._lock = RLock()

    def create_idempotent(self, draft: CatalogIntakeDraft) -> CatalogIntakeDraft:
        with self._lock:
            existing = self._drafts.get(draft.intake_id)
            if existing is not None and existing != draft:
                raise CatalogIntakeDraftConflictError(
                    f"Catalog intake {draft.intake_id} already contains a different draft"
                )
            stored = self._drafts.setdefault(draft.intake_id, draft.model_copy(deep=True))
            return stored.model_copy(deep=True)

    def get(self, intake_id: str) -> CatalogIntakeDraft | None:
        with self._lock:
            draft = self._drafts.get(intake_id)
            return draft.model_copy(deep=True) if draft else None

    def list_all(self) -> list[CatalogIntakeDraft]:
        with self._lock:
            return [
                self._drafts[intake_id].model_copy(deep=True)
                for intake_id in sorted(self._drafts)
            ]

    def clear(self) -> None:
        with self._lock:
            self._drafts.clear()


class PostgresCatalogIntakeDraftStore:
    durable = True

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or get_database_url()
        if not self.database_url:
            raise PersistenceUnavailableError(
                "Catalog intake PostgreSQL storage requires DATABASE_URL"
            )

    def _connect(self):
        try:
            import psycopg2

            return psycopg2.connect(self.database_url, connect_timeout=5)
        except Exception as exc:
            raise PersistenceUnavailableError(
                "Configured catalog intake PostgreSQL storage is unavailable"
            ) from exc

    def create_idempotent(self, draft: CatalogIntakeDraft) -> CatalogIntakeDraft:
        data = _serialized(draft)
        fingerprint = _fingerprint(draft)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"catalog-intake:{draft.intake_id}",),
                )
                cur.execute(
                    """SELECT request_fingerprint, data
                       FROM catalog_intake_drafts
                       WHERE intake_id = %s
                       FOR UPDATE""",
                    (draft.intake_id,),
                )
                row = cur.fetchone()
                if row:
                    if row[0] != fingerprint:
                        raise CatalogIntakeDraftConflictError(
                            f"Catalog intake {draft.intake_id} already contains a different draft"
                        )
                    persisted = CatalogIntakeDraft.model_validate(_decoded(row[1]))
                    conn.commit()
                    return persisted
                cur.execute(
                    """INSERT INTO catalog_intake_drafts (
                           intake_id, request_fingerprint, catalog_item_id,
                           repository_url, revision, state, data
                       ) VALUES (%s, %s, %s, %s, %s, 'draft', %s::jsonb)""",
                    (
                        draft.intake_id,
                        fingerprint,
                        draft.requested.catalog_item_id,
                        draft.release_identity.repository_url,
                        draft.release_identity.revision,
                        data,
                    ),
                )
            conn.commit()
            return draft.model_copy(deep=True)
        except CatalogIntakeDraftConflictError:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            logger.warning("Catalog intake draft persistence failed: %s", exc)
            raise PersistenceUnavailableError(
                "Catalog intake draft could not be durably persisted"
            ) from exc
        finally:
            conn.close()

    def get(self, intake_id: str) -> CatalogIntakeDraft | None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM catalog_intake_drafts WHERE intake_id = %s",
                    (intake_id,),
                )
                row = cur.fetchone()
                return CatalogIntakeDraft.model_validate(_decoded(row[0])) if row else None
        except Exception as exc:
            logger.warning("Catalog intake draft read failed: %s", exc)
            raise PersistenceUnavailableError(
                "Catalog intake draft could not be durably read"
            ) from exc
        finally:
            conn.close()

    def list_all(self) -> list[CatalogIntakeDraft]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data FROM catalog_intake_drafts ORDER BY intake_id"
                )
                return [
                    CatalogIntakeDraft.model_validate(_decoded(row[0]))
                    for row in cur.fetchall()
                ]
        except Exception as exc:
            logger.warning("Catalog intake draft listing failed: %s", exc)
            raise PersistenceUnavailableError(
                "Catalog intake drafts could not be durably listed"
            ) from exc
        finally:
            conn.close()
