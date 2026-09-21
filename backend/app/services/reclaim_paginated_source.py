"""Read-only paginated adapter for a *supplied* reclaim-inventory provider.

It checks transport-level completeness and snapshot identity before passing rows
to the balancing collector. No database, Kubernetes, HTTP or deletion client is
created here. A provider's truthful count and source identity remain external
authority requirements, not facts this adapter can independently establish.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.services.reclaim_inventory_collector import CollectionBatch, InventoryCollectionError


@dataclass(frozen=True)
class InventoryPage:
    rows: list[Mapping[str, Any]]
    source_id: str
    revision: str
    total_count: int
    cursor: str | None
    next_cursor: str | None
    observed_at: datetime


class InventoryPageProvider(Protocol):
    """Supply one read-only page pinned to the requested source revision."""

    def fetch_page(
        self,
        collection: str,
        *,
        cursor: str | None,
        workshop_ids: frozenset[str] | None,
        cluster_ref: str | None,
        expected_revision: str | None,
    ) -> InventoryPage: ...


_ROW_KEYS = {
    "clusters": "cluster_ref",
    "workshops": "workshop_id",
    "sessions": "session_id",
    "reservations": "reservation_id",
    "namespaces": "namespace",
}
_ROW_LIMITS = {
    "clusters": 100,
    "workshops": 100,
    "sessions": 5000,
    "reservations": 100,
    "namespaces": 5000,
}
_MAX_PAGES = 1000


def _opaque(value: Any, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit and value.isprintable()


class PaginatedReclaimSource:
    """Implement the collector protocol with verified pagination boundaries.

    Database lists share one pinned revision. Each cluster namespace list has
    its own pinned revision. A configured source ID is checked on every page;
    it is not inferred from an untrusted row or provider error message.
    """

    def __init__(
        self,
        provider: InventoryPageProvider,
        *,
        database_source_id: str,
        namespace_source_ids: Mapping[str, str],
        now: datetime | None = None,
        max_age: timedelta = timedelta(minutes=30),
    ) -> None:
        if (
            not _opaque(database_source_id, 128)
            or not isinstance(namespace_source_ids, Mapping)
            or not namespace_source_ids
            or any(
                not _opaque(cluster, 63) or not _opaque(source_id, 128)
                for cluster, source_id in namespace_source_ids.items()
            )
            or len(set(namespace_source_ids.values())) != len(namespace_source_ids)
            or database_source_id in namespace_source_ids.values()
        ):
            raise InventoryCollectionError("invalid configured source identities")
        self._now = now if now is not None else datetime.now(UTC)
        if (
            not isinstance(self._now, datetime)
            or self._now.tzinfo is None
            or self._now.utcoffset() is None
            or not isinstance(max_age, timedelta)
            or max_age <= timedelta(0)
        ):
            raise InventoryCollectionError("invalid collection time or freshness window")
        self._provider = provider
        self._database_source_id = database_source_id
        self._namespace_source_ids = dict(namespace_source_ids)
        self._max_age = max_age
        self._database_revision: str | None = None
        self._cluster_refs: frozenset[str] | None = None
        self._workshop_ids: frozenset[str] | None = None

    def _scan(
        self,
        collection: str,
        *,
        source_id: str,
        expected_revision: str | None,
        workshop_ids: frozenset[str] | None = None,
        cluster_ref: str | None = None,
    ) -> tuple[CollectionBatch, str]:
        rows: list[Mapping[str, Any]] = []
        keys: set[str] = set()
        cursor: str | None = None
        seen_cursors: set[str] = set()
        revision = expected_revision
        total_count: int | None = None
        timestamps: list[datetime] = []
        for _ in range(_MAX_PAGES):
            try:
                page = self._provider.fetch_page(
                    collection,
                    cursor=cursor,
                    workshop_ids=workshop_ids,
                    cluster_ref=cluster_ref,
                    expected_revision=revision,
                )
            except Exception:  # noqa: BLE001 - provider errors may contain secrets
                raise InventoryCollectionError("inventory page fetch failed") from None
            if not isinstance(page, InventoryPage):
                raise InventoryCollectionError("inventory page has invalid shape")
            if page.source_id != source_id:
                raise InventoryCollectionError("inventory page source identity mismatch")
            if not _opaque(page.revision, 128) or (
                revision is not None and page.revision != revision
            ):
                raise InventoryCollectionError("inventory page revision changed")
            revision = page.revision
            if page.cursor != cursor:
                raise InventoryCollectionError("inventory page cursor mismatch")
            if (
                type(page.total_count) is not int
                or not 0 <= page.total_count <= _ROW_LIMITS[collection]
            ):
                raise InventoryCollectionError("inventory page count is invalid")
            if total_count is not None and page.total_count != total_count:
                raise InventoryCollectionError("inventory page count changed")
            total_count = page.total_count
            if (
                not isinstance(page.observed_at, datetime)
                or page.observed_at.tzinfo is None
                or page.observed_at.utcoffset() is None
                or not timedelta(0) <= self._now - page.observed_at <= self._max_age
            ):
                raise InventoryCollectionError("inventory page is stale or future-dated")
            timestamps.append(page.observed_at)
            if not isinstance(page.rows, list) or len(page.rows) > _ROW_LIMITS[collection]:
                raise InventoryCollectionError("inventory page rows are invalid")
            if page.next_cursor is not None and not page.rows:
                raise InventoryCollectionError("inventory page is incomplete")
            for row in page.rows:
                if not isinstance(row, Mapping):
                    raise InventoryCollectionError("inventory page row is invalid")
                key = row.get(_ROW_KEYS[collection])
                if not _opaque(key, 512) or key in keys:
                    raise InventoryCollectionError("inventory page has invalid or duplicate row ID")
                keys.add(key)
                rows.append(row)
            if len(rows) > total_count:
                raise InventoryCollectionError("inventory page count is inconsistent")
            if page.next_cursor is None:
                if len(rows) != total_count:
                    raise InventoryCollectionError("inventory page is incomplete")
                return CollectionBatch(rows, True, min(timestamps)), revision
            if (
                not _opaque(page.next_cursor, 512)
                or page.next_cursor in seen_cursors
                or len(rows) == total_count
            ):
                raise InventoryCollectionError("inventory page cursor or count is inconsistent")
            seen_cursors.add(page.next_cursor)
            cursor = page.next_cursor
        raise InventoryCollectionError("inventory page limit exceeded")

    def list_cluster_refs(self) -> CollectionBatch:
        if self._database_revision is not None:
            raise InventoryCollectionError("cluster roster was already read")
        batch, revision = self._scan(
            "clusters", source_id=self._database_source_id, expected_revision=None
        )
        observed = frozenset(row["cluster_ref"] for row in batch.rows)
        if observed != self._namespace_source_ids.keys():
            raise InventoryCollectionError(
                "configured namespace sources do not match cluster roster"
            )
        self._database_revision = revision
        self._cluster_refs = observed
        return batch

    def list_retained_workshops(self) -> CollectionBatch:
        if self._database_revision is None:
            raise InventoryCollectionError("cluster roster must be read first")
        batch, _ = self._scan(
            "workshops",
            source_id=self._database_source_id,
            expected_revision=self._database_revision,
        )
        self._workshop_ids = frozenset(row["workshop_id"] for row in batch.rows)
        return batch

    def list_sessions(self, workshop_ids: frozenset[str]) -> CollectionBatch:
        self._check_workshop_scope(workshop_ids)
        batch, _ = self._scan(
            "sessions",
            source_id=self._database_source_id,
            expected_revision=self._database_revision,
            workshop_ids=workshop_ids,
        )
        return batch

    def list_reservations(self, workshop_ids: frozenset[str]) -> CollectionBatch:
        self._check_workshop_scope(workshop_ids)
        batch, _ = self._scan(
            "reservations",
            source_id=self._database_source_id,
            expected_revision=self._database_revision,
            workshop_ids=workshop_ids,
        )
        return batch

    def _check_workshop_scope(self, workshop_ids: frozenset[str]) -> None:
        if self._workshop_ids is None or workshop_ids != self._workshop_ids:
            raise InventoryCollectionError("workshop source scope changed")

    def list_managed_namespaces(self, cluster_ref: str) -> CollectionBatch:
        if self._cluster_refs is None or cluster_ref not in self._cluster_refs:
            raise InventoryCollectionError("namespace cluster is not in registered roster")
        batch, _ = self._scan(
            "namespaces",
            source_id=self._namespace_source_ids[cluster_ref],
            expected_revision=None,
            cluster_ref=cluster_ref,
        )
        return batch
