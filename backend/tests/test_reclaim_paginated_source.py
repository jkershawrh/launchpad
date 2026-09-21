"""A paginated source cannot claim completeness without exhausting its snapshot."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.services.reclaim_inventory_collector import (
    InventoryCollectionError,
    build_reclaim_inventory,
)
from app.services.reclaim_paginated_source import InventoryPage, PaginatedReclaimSource

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
WORKSHOP = str(UUID("11111111-1111-4111-8111-111111111111"))
SESSION = str(UUID("22222222-2222-4222-8222-222222222222"))


class FakeProvider:
    def __init__(self):
        self.pages = {
            ("clusters", None, None): self.page(
                [{"cluster_ref": "arena"}, {"cluster_ref": "brutus"}],
                "database:launchpad",
                "db-7",
                2,
            ),
            ("workshops", None, None): self.page(
                [
                    {
                        "workshop_id": WORKSHOP,
                        "cluster_ref": "arena",
                        "seat_count": 1,
                        "reservation_id": "event:one",
                        "state": "ready",
                        "email": "private@example.org",
                    }
                ],
                "database:launchpad",
                "db-7",
                1,
            ),
            ("sessions", None, None): self.page(
                [
                    {
                        "session_id": SESSION,
                        "workshop_id": WORKSHOP,
                        "cluster_ref": "arena",
                        "namespace": "launchpad-seat-1",
                        "seat_number": 1,
                        "state": "ready",
                    }
                ],
                "database:launchpad",
                "db-7",
                1,
            ),
            ("reservations", None, None): self.page(
                [
                    {
                        "reservation_id": "event:one",
                        "workshop_id": WORKSHOP,
                        "cluster_ref": "arena",
                        "seat_count": 1,
                        "state": "consumed",
                    }
                ],
                "database:launchpad",
                "db-7",
                1,
            ),
            ("namespaces", "arena", None): self.page(
                [
                    {
                        "namespace": "launchpad-seat-1",
                        "cluster_ref": "arena",
                        "workshop_id": WORKSHOP,
                        "session_id": SESSION,
                        "token": "private-token",
                    }
                ],
                "cluster:arena",
                "rv-4",
                1,
            ),
            ("namespaces", "brutus", None): self.page([], "cluster:brutus", "rv-3", 0),
        }
        self.calls = []

    @staticmethod
    def page(rows, source_id, revision, total_count, cursor=None, next_cursor=None):
        return InventoryPage(
            rows=rows,
            source_id=source_id,
            revision=revision,
            total_count=total_count,
            cursor=cursor,
            next_cursor=next_cursor,
            observed_at=NOW,
        )

    def fetch_page(self, collection, *, cursor, workshop_ids, cluster_ref, expected_revision):
        self.calls.append((collection, cluster_ref, cursor, workshop_ids, expected_revision))
        return self.pages[(collection, cluster_ref, cursor)]


def build(source):
    return build_reclaim_inventory(
        PaginatedReclaimSource(
            source,
            database_source_id="database:launchpad",
            namespace_source_ids={"arena": "cluster:arena", "brutus": "cluster:brutus"},
            now=NOW,
        ),
        now=NOW,
    )


def test_complete_snapshot_projects_private_fields_and_pins_database_revision():
    source = FakeProvider()
    payload = build(source)
    assert payload["scope"]["cluster_refs"] == ["arena", "brutus"]
    assert "private" not in str(payload)
    assert all(
        call[4] == "db-7"
        for call in source.calls
        if call[0] in {"workshops", "sessions", "reservations"}
    )
    assert all(
        call[3] == frozenset({WORKSHOP})
        for call in source.calls
        if call[0] in {"sessions", "reservations"}
    )
    assert ("namespaces", "brutus", None, None, None) in source.calls


@pytest.mark.parametrize(
    "collection,cluster",
    [
        ("clusters", None),
        ("workshops", None),
        ("sessions", None),
        ("reservations", None),
        ("namespaces", "arena"),
    ],
)
def test_count_mismatch_fails_closed(collection, cluster):
    source = FakeProvider()
    key = (collection, cluster, None)
    source.pages[key] = replace(source.pages[key], total_count=source.pages[key].total_count + 1)
    with pytest.raises(InventoryCollectionError, match="incomplete"):
        build(source)


def test_paginated_exhaustion_succeeds_with_stable_revision():
    source = FakeProvider()
    first = source.pages[("clusters", None, None)]
    source.pages[("clusters", None, None)] = replace(
        first, rows=first.rows[:1], next_cursor="page-2"
    )
    source.pages[("clusters", None, "page-2")] = replace(
        first, rows=first.rows[1:], cursor="page-2"
    )
    assert build(source)["scope"]["cluster_refs"] == ["arena", "brutus"]
    assert ("clusters", None, "page-2", None, "db-7") in source.calls


@pytest.mark.parametrize(
    "mutation",
    [
        {"revision": "db-8"},
        {"source_id": "database:imposter"},
        {"total_count": 3},
        {"cursor": "wrong"},
        {"observed_at": NOW - timedelta(minutes=31)},
    ],
)
def test_inconsistent_second_page_fails_closed(mutation):
    source = FakeProvider()
    first = source.pages[("clusters", None, None)]
    source.pages[("clusters", None, None)] = replace(
        first, rows=first.rows[:1], next_cursor="page-2"
    )
    source.pages[("clusters", None, "page-2")] = replace(
        first, **{"rows": first.rows[1:], "cursor": "page-2", **mutation}
    )
    with pytest.raises(InventoryCollectionError):
        build(source)


def test_repeated_cursor_and_duplicate_row_fail_closed():
    source = FakeProvider()
    first = source.pages[("clusters", None, None)]
    source.pages[("clusters", None, None)] = replace(
        first, rows=first.rows[:1], next_cursor="again"
    )
    source.pages[("clusters", None, "again")] = replace(
        first, rows=first.rows[:1], cursor="again", next_cursor="again"
    )
    with pytest.raises(InventoryCollectionError):
        build(source)


def test_cluster_source_identity_must_match_configured_cluster():
    source = FakeProvider()
    key = ("namespaces", "arena", None)
    source.pages[key] = replace(source.pages[key], source_id="cluster:brutus")
    with pytest.raises(InventoryCollectionError, match="source identity"):
        build(source)


def test_database_revision_must_match_across_all_rosters():
    source = FakeProvider()
    key = ("sessions", None, None)
    source.pages[key] = replace(source.pages[key], revision="db-8")
    with pytest.raises(InventoryCollectionError, match="revision changed"):
        build(source)


def test_configured_cluster_sources_must_cover_exact_registered_roster():
    source = FakeProvider()
    adapter = PaginatedReclaimSource(
        source,
        database_source_id="database:launchpad",
        namespace_source_ids={"arena": "cluster:arena"},
        now=NOW,
    )
    with pytest.raises(InventoryCollectionError, match="cluster roster"):
        build_reclaim_inventory(adapter, now=NOW)


def test_database_and_cluster_source_id_cannot_be_the_same():
    with pytest.raises(InventoryCollectionError, match="source identities"):
        PaginatedReclaimSource(
            FakeProvider(),
            database_source_id="database:launchpad",
            namespace_source_ids={"arena": "database:launchpad"},
            now=NOW,
        )


def test_duplicate_namespace_across_pages_is_rejected():
    source = FakeProvider()
    key = ("namespaces", "arena", None)
    first = source.pages[key]
    source.pages[key] = replace(first, next_cursor="next", total_count=2)
    source.pages[("namespaces", "arena", "next")] = replace(first, cursor="next", total_count=2)
    with pytest.raises(InventoryCollectionError, match="duplicate"):
        build(source)


def test_missing_scoped_session_fails_even_when_source_understates_count():
    source = FakeProvider()
    key = ("sessions", None, None)
    source.pages[key] = replace(source.pages[key], rows=[], total_count=0)
    with pytest.raises(InventoryCollectionError, match="seat count"):
        build(source)


def test_provider_error_suppresses_secret():
    source = FakeProvider()

    def bad(*_args, **_kwargs):
        raise RuntimeError("password=private-secret")

    source.fetch_page = bad
    with pytest.raises(InventoryCollectionError) as caught:
        build(source)
    assert "private-secret" not in str(caught.value)
