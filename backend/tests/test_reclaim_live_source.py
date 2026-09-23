"""Read-only source proof: persisted seats must match target-cluster namespaces."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.services.reclaim_inventory_collector import (
    InventoryCollectionError,
    build_reclaim_inventory,
)
from app.services.reclaim_live_source import (
    DatabaseRoster,
    LiveReclaimInventorySource,
    PostgresReclaimRosterReader,
    main,
)

NOW = datetime(2026, 9, 21, 16, 0, tzinfo=UTC)
WORKSHOP = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"


def namespace(*, session=SESSION, workshop=WORKSHOP, cluster="arena", name="launchpad-seat-1"):
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            labels={
                "launchpad.redhat.com/session-id": session,
                "launchpad.redhat.com/workshop-id": workshop,
                "launchpad.redhat.com/cluster-id": cluster,
            },
        )
    )


def page(items, version="rv-1"):
    return SimpleNamespace(
        items=items,
        metadata=SimpleNamespace(resource_version=version, _continue=""),
    )


class FakeCore:
    def __init__(self, scans):
        self.scans = iter(scans)
        self.calls = 0

    def list_namespace(self, **kwargs):
        self.calls += 1
        return page(next(self.scans))


class FakeFactory:
    def __init__(self, core):
        self.core = core
        self.calls = []

    def clients(self, cluster_id, *, allow_disabled=False):
        self.calls.append((cluster_id, allow_disabled))
        return SimpleNamespace(core=self.core)


class FakeRegistry:
    def list_all(self):
        return [SimpleNamespace(cluster_id="arena")]


class FakeReader:
    def read(self):
        return DatabaseRoster(
            observed_at=NOW,
            workshops=(
                {
                    "workshop_id": WORKSHOP,
                    "cluster_ref": "arena",
                    "seat_count": 1,
                    "reservation_id": None,
                    "state": "ready",
                },
            ),
            sessions=(
                {
                    "session_id": SESSION,
                    "workshop_id": WORKSHOP,
                    "cluster_ref": "arena",
                    "namespace": "launchpad-seat-1",
                    "seat_number": 1,
                    "state": "ready",
                },
            ),
            reservations=(),
        )


def build(core):
    factory = FakeFactory(core)
    source = LiveReclaimInventorySource(
        FakeReader(),
        FakeRegistry(),
        factory,
        clock=lambda: NOW,
    )
    result = build_reclaim_inventory(source, now=NOW)
    return result, factory


def test_live_source_balances_persisted_roster_with_twice_scanned_namespace():
    core = FakeCore([[namespace()], [namespace()]])
    result, factory = build(core)
    assert result["scope"]["namespaces_complete"] is True
    assert result["namespaces"] == [
        {
            "namespace": "launchpad-seat-1",
            "cluster_ref": "arena",
            "workshop_id": WORKSHOP,
            "session_id": SESSION,
        }
    ]
    assert core.calls == 2
    assert factory.calls == [("arena", True)]


def test_unrelated_individual_lab_does_not_block_workshop_inventory():
    unrelated = namespace(session="unrelated", workshop="", cluster="brutus", name="other-lab")
    core = FakeCore([[namespace(), unrelated], [namespace(), unrelated]])
    result, _ = build(core)
    assert len(result["namespaces"]) == 1


@pytest.mark.parametrize(
    "scans",
    [
        [[namespace()], []],
        [[namespace(cluster="brutus")], [namespace(cluster="brutus")]],
        [[namespace(session="33333333-3333-4333-8333-333333333333")]] * 2,
    ],
)
def test_namespace_drift_or_wrong_ownership_fails_closed(scans):
    with pytest.raises(InventoryCollectionError):
        build(FakeCore(scans))


def test_cluster_client_failure_does_not_reveal_credentials():
    class BrokenCore:
        def list_namespace(self, **_kwargs):
            raise RuntimeError("password=private-secret")

    with pytest.raises(InventoryCollectionError) as caught:
        build(BrokenCore())
    assert "private-secret" not in str(caught.value)


def test_operator_entry_point_emits_only_a_complete_snapshot(capsys):
    source = LiveReclaimInventorySource(
        FakeReader(),
        FakeRegistry(),
        FakeFactory(FakeCore([[namespace()], [namespace()]])),
        clock=lambda: NOW,
    )
    assert main(source, now=NOW) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["scope"]["workshop_ids"] == [WORKSHOP]
    assert captured.err == ""


def test_operator_entry_point_has_no_partial_output_on_failure(capsys):
    source = LiveReclaimInventorySource(
        FakeReader(),
        FakeRegistry(),
        FakeFactory(FakeCore([[namespace()], []])),
        clock=lambda: NOW,
    )
    assert main(source, now=NOW) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "read-only reclaim inventory blocked\n"


class FakeCursor:
    def __init__(self, results):
        self.results = iter(results)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchall(self):
        return next(self.results)


class FakeConnection:
    def __init__(self, results):
        self.cur = FakeCursor(results)
        self.session = None
        self.rolled_back = False
        self.closed = False

    def set_session(self, **kwargs):
        self.session = kwargs

    def cursor(self):
        return self.cur

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_postgres_roster_uses_one_read_only_snapshot_and_projects_private_fields():
    workshop = {
        "workshop_id": WORKSHOP,
        "tenant_id": "tenant",
        "catalog_item_id": "lab",
        "num_users": 1,
        "cluster_ref": "arena",
        "status": "ready",
        "session_ids": [SESSION],
        "seats": [{"workshop_id": WORKSHOP, "seat_number": 1, "session_id": SESSION}],
    }
    session = {
        "session_id": SESSION,
        "request_id": "request",
        "tenant_id": "tenant",
        "catalog_item_id": "lab",
        "namespace": "launchpad-seat-1",
        "cluster_ref": "arena",
        "status": "ready",
        "maas_api_key": "private-secret",
    }
    conn = FakeConnection([[(workshop,)], [(session,)]])
    roster = PostgresReclaimRosterReader(lambda: conn, clock=lambda: NOW).read()
    assert conn.session == {"readonly": True, "isolation_level": "REPEATABLE READ"}
    assert conn.rolled_back and conn.closed
    assert len(conn.cur.queries) == 2
    assert roster.sessions[0]["seat_number"] == 1
    assert "private-secret" not in str(roster)


def test_missing_persisted_session_rejects_roster_without_leaking_details():
    workshop = {
        "workshop_id": WORKSHOP,
        "tenant_id": "tenant",
        "catalog_item_id": "lab",
        "num_users": 1,
        "cluster_ref": "arena",
        "status": "ready",
        "session_ids": [SESSION],
        "seats": [{"workshop_id": WORKSHOP, "seat_number": 1, "session_id": SESSION}],
    }
    conn = FakeConnection([[(workshop,)], []])
    with pytest.raises(InventoryCollectionError) as caught:
        PostgresReclaimRosterReader(lambda: conn, clock=lambda: NOW).read()
    assert conn.rolled_back and conn.closed
    assert "private-secret" not in str(caught.value)
