from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.domain.events import (
    EventCapacitySupply,
    EventCatalogCapacity,
    EventClusterCapacity,
    EventManifest,
    calculate_event_capacity,
)


def _manifest(*, exposure_policy: str = "public_code") -> EventManifest:
    return EventManifest.model_validate(
        {
            "event_id": "matrix-proof",
            "name": "Capacity matrix proof",
            "owner": "event-owner",
            "technical_approver": "technical-owner",
            "exposure_policy": exposure_policy,
            "placement_policy": "single_cluster_per_workshop",
            "cohorts": [
                {
                    "cohort_id": "wave-1",
                    "participants": 30,
                    "lab_refs": ["serve", "agent"],
                }
            ],
            "labs": [
                {
                    "lab_ref": "serve",
                    "catalog_id": "serve-llms",
                    "catalog_release": "v1",
                    "required_capabilities": ["cpu", "model-endpoint"],
                },
                {
                    "lab_ref": "agent",
                    "catalog_id": "build-agent",
                    "catalog_release": "v2",
                    "required_capabilities": ["cpu", "model-endpoint"],
                },
            ],
            "retention": {"hours": 8, "starts_from": "cohort_start"},
            "approval": {
                "event_owner_approved": True,
                "technical_approver_approved": True,
                "approved_seat_environments": 60,
                "approved_retention_hours": 8,
            },
        }
    )


def _cluster(
    cluster_id: str,
    *,
    certified_seats: int,
    catalogs: list[tuple[str, str, int]],
    exposure_policies: list[str] | None = None,
    enabled: bool = True,
    dr_reserved_seats: int = 0,
    uncertified_seats: int = 0,
) -> EventClusterCapacity:
    return EventClusterCapacity(
        cluster_id=cluster_id,
        enabled=enabled,
        priority=10,
        exposure_policies=exposure_policies or ["internal", "public_code"],
        capabilities=["cpu", "model-endpoint"],
        certified_seats=certified_seats,
        dr_reserved_seats=dr_reserved_seats,
        uncertified_seats=uncertified_seats,
        catalogs=[
            EventCatalogCapacity(
                catalog_id=catalog_id,
                catalog_release=release,
                certified_seats=seats,
            )
            for catalog_id, release, seats in catalogs
        ],
    )


def test_matrix_allocates_each_exact_catalog_release_deterministically():
    preview = calculate_event_capacity(
        _manifest(),
        EventCapacitySupply(
            clusters=[
                _cluster("arena", certified_seats=30, catalogs=[("serve-llms", "v1", 30)]),
                _cluster("brutus", certified_seats=30, catalogs=[("build-agent", "v2", 30)]),
            ]
        ),
    )

    assert preview.eligible is True
    assert preview.capacity_shortfall == 0
    assert [item.model_dump() for item in preview.allocations] == [
        {
            "cohort_id": "wave-1",
            "lab_ref": "agent",
            "catalog_id": "build-agent",
            "catalog_release": "v2",
            "cluster_id": "brutus",
            "seats": 30,
        },
        {
            "cohort_id": "wave-1",
            "lab_ref": "serve",
            "catalog_id": "serve-llms",
            "catalog_release": "v1",
            "cluster_id": "arena",
            "seats": 30,
        },
    ]


def test_cluster_total_prevents_catalog_cells_from_double_counting_capacity():
    preview = calculate_event_capacity(
        _manifest(),
        EventCapacitySupply(
            clusters=[
                _cluster(
                    "arena",
                    certified_seats=30,
                    catalogs=[
                        ("serve-llms", "v1", 30),
                        ("build-agent", "v2", 30),
                    ],
                )
            ]
        ),
    )

    assert preview.certified_capacity == 30
    assert preview.capacity_shortfall == 30
    assert preview.eligible is False


def test_one_workshop_is_never_split_across_clusters():
    manifest = _manifest()
    manifest.cohorts[0].lab_refs = ["serve"]
    manifest.approval.approved_seat_environments = 30
    preview = calculate_event_capacity(
        manifest,
        EventCapacitySupply(
            clusters=[
                _cluster(
                    "arena",
                    certified_seats=15,
                    catalogs=[("serve-llms", "v1", 15)],
                ),
                _cluster(
                    "brutus",
                    certified_seats=15,
                    catalogs=[("serve-llms", "v1", 15)],
                ),
            ]
        ),
    )

    assert preview.certified_capacity == 30
    assert preview.allocations == []
    assert preview.capacity_shortfall == 30
    assert preview.eligible is False


def test_allocator_fails_closed_above_bounded_workshop_limit():
    payload = _manifest().model_dump(mode="json")
    payload["cohorts"] = [
        {"cohort_id": f"wave-{index}", "participants": 1, "lab_refs": ["serve"]}
        for index in range(101)
    ]
    payload["approval"]["approved_seat_environments"] = 101
    manifest = EventManifest.model_validate(payload)

    with pytest.raises(ValueError, match="101 atomic workshops; maximum is 100"):
        calculate_event_capacity(manifest, EventCapacitySupply())


def test_allocator_reroutes_flexible_demand_to_preserve_constrained_capacity():
    manifest = _manifest()
    manifest.labs[0].lab_ref = "a-flexible"
    manifest.cohorts[0].lab_refs[0] = "a-flexible"
    manifest.labs[1].lab_ref = "z-constrained"
    manifest.cohorts[0].lab_refs[1] = "z-constrained"
    supply = EventCapacitySupply(
        clusters=[
            _cluster(
                "arena",
                certified_seats=30,
                catalogs=[("serve-llms", "v1", 30), ("build-agent", "v2", 30)],
            ),
            _cluster(
                "brutus",
                certified_seats=30,
                catalogs=[("serve-llms", "v1", 30)],
            ),
        ]
    )

    preview = calculate_event_capacity(manifest, supply)

    assert preview.eligible is True
    assert {(item.lab_ref, item.cluster_id) for item in preview.allocations} == {
        ("a-flexible", "brutus"),
        ("z-constrained", "arena"),
    }


def test_public_event_cannot_consume_internal_only_certification():
    preview = calculate_event_capacity(
        _manifest(),
        EventCapacitySupply(
            clusters=[
                _cluster(
                    "arena",
                    certified_seats=60,
                    catalogs=[("serve-llms", "v1", 30), ("build-agent", "v2", 30)],
                    exposure_policies=["internal"],
                )
            ]
        ),
    )

    assert preview.certified_capacity == 0
    assert preview.capacity_shortfall == 60
    assert preview.allocations == []


def test_exact_release_and_capability_are_both_required():
    supply = EventCapacitySupply(
        clusters=[
            _cluster(
                "arena",
                certified_seats=60,
                catalogs=[("serve-llms", "old", 30), ("build-agent", "v2", 30)],
            )
        ]
    )
    supply.clusters[0].capabilities = ["cpu"]

    preview = calculate_event_capacity(_manifest(), supply)

    assert preview.capacity_shortfall == 60
    assert all(item.allocated_seats == 0 for item in preview.lab_capacity)


def test_dr_reserved_and_uncertified_matrix_capacity_is_visible_but_not_placeable():
    preview = calculate_event_capacity(
        _manifest(),
        EventCapacitySupply(
            clusters=[
                _cluster(
                    "flightpath",
                    enabled=False,
                    certified_seats=0,
                    dr_reserved_seats=60,
                    uncertified_seats=60,
                    catalogs=[("serve-llms", "v1", 30), ("build-agent", "v2", 30)],
                )
            ]
        ),
    )

    assert preview.certified_capacity == 0
    assert preview.dr_reserved_capacity == 60
    assert preview.uncertified_capacity == 60
    assert preview.capacity_shortfall == 60
    assert preview.eligible is False


def test_matrix_contract_declares_cluster_catalog_and_allocation_shapes():
    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts" / "event-manifest-v1.yaml").read_text()
    )
    schemas = contract["components"]["schemas"]

    assert contract["info"]["version"] == "1.4.0"
    assert "EventClusterCapacity" in schemas
    assert "EventCatalogCapacity" in schemas
    assert "EventResourceVector" in schemas
    assert "EventCapacityAllocation" in schemas
    assert "EventLabCapacityDecision" in schemas
    preview = schemas["EventCapacityPreview"]
    assert {"allocations", "lab_capacity"} <= set(preview["required"])
    assert "resources_per_seat" in schemas["EventCatalogCapacity"]["required"]
    assert "resource_capacity" in schemas["EventClusterCapacity"]["required"]
