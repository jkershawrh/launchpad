"""The file boundary must not turn malformed accounting into admission evidence."""

import json
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from app.services.event_inflight_capacity_provider import (
    EventInflightCapacityUnavailableError,
    FileEventInflightCapacityProvider,
)


def _document():
    return {
        "schema_version": "1.0",
        "observed_at": "2026-09-21T18:00:00Z",
        "clusters": [
            {
                "cluster_id": "arena",
                "allocatable": {
                    "cpu_millicores": 8000,
                    "memory_mib": 16384,
                    "pods": 30,
                    "model_slots": 4,
                },
                "accounting_complete": True,
                "workloads": [
                    {
                        "namespace": "seat-one",
                        "reservation_id": "event:cohort:lab",
                        "workshop_id": "workshop-one",
                        "seat_refs": ["seat-1"],
                        "resources": {
                            "cpu_millicores": 1000,
                            "memory_mib": 1024,
                            "pods": 2,
                            "model_slots": 1,
                        },
                    }
                ],
            }
        ],
    }


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")


def test_loads_versioned_snapshot_and_hashes_exact_source_bytes(tmp_path):
    path = tmp_path / "inflight.json"
    _write(path, _document())
    raw = path.read_bytes()
    snapshot = FileEventInflightCapacityProvider(path).load()
    assert snapshot.snapshot_id == "sha256:" + sha256(raw).hexdigest()
    assert snapshot.observed_at == datetime(2026, 9, 21, 18, tzinfo=UTC)
    assert snapshot.clusters[0].workloads[0].resources.cpu_millicores == 1000


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version="2.0"),
        lambda d: d.update(snapshot_id="sha256:" + "0" * 64),
        lambda d: d.update(unexpected="ignored"),
        lambda d: d.update(observed_at="2026-09-21T18:00:00"),
        lambda d: d.update(clusters=[]),
        lambda d: d["clusters"][0].update(accounting_complete="true"),
        lambda d: d["clusters"][0].update(cluster_id=" "),
        lambda d: d["clusters"][0]["allocatable"].update(pods="30"),
        lambda d: d["clusters"][0]["allocatable"].update(cpu_millicores=True),
        lambda d: d["clusters"][0]["allocatable"].update(extra=1),
        lambda d: d["clusters"][0]["workloads"][0].update(seat_refs=["seat-1", "seat-1"]),
        lambda d: d["clusters"][0]["workloads"][0].update(namespace=" "),
        lambda d: d["clusters"][0]["workloads"][0].update(reservation_id=17),
        lambda d: d["clusters"][0]["workloads"][0].update(seat_refs="seat-1"),
        lambda d: d["clusters"][0]["workloads"].append(d["clusters"][0]["workloads"][0].copy()),
        lambda d: d["clusters"][0]["workloads"][0]["resources"].update(pods=-1),
        lambda d: d["clusters"].append(d["clusters"][0].copy()),
    ],
)
def test_rejects_untrusted_or_ambiguous_input(tmp_path, mutate):
    path = tmp_path / "inflight.json"
    document = _document()
    mutate(document)
    _write(path, document)
    with pytest.raises(EventInflightCapacityUnavailableError):
        FileEventInflightCapacityProvider(path).load()


@pytest.mark.parametrize("raw", [b"{", b"[]", b"null", b"", b"\xff"])
def test_rejects_unparseable_or_non_object_files(tmp_path, raw):
    path = tmp_path / "inflight.json"
    path.write_bytes(raw)
    with pytest.raises(EventInflightCapacityUnavailableError):
        FileEventInflightCapacityProvider(path).load()


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(EventInflightCapacityUnavailableError):
        FileEventInflightCapacityProvider(tmp_path / "missing.json").load()


def test_duplicate_json_keys_fail_closed(tmp_path):
    path = tmp_path / "inflight.json"
    path.write_text('{"schema_version":"1.0","schema_version":"1.0"}')
    with pytest.raises(EventInflightCapacityUnavailableError):
        FileEventInflightCapacityProvider(path).load()


def test_oversized_evidence_fails_closed(tmp_path):
    path = tmp_path / "inflight.json"
    path.write_bytes(b" " * (8 * 1024 * 1024 + 1))
    with pytest.raises(EventInflightCapacityUnavailableError):
        FileEventInflightCapacityProvider(path).load()
