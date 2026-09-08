"""CDD/TDD contract for the operator observability read model."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from app.domain.enums import SessionStatus, WorkshopSeatStatus, WorkshopStatus
from app.domain.models import LabSession, LifecycleEvent, Workshop, WorkshopSeat


def _session(
    session_id: str,
    *,
    status: SessionStatus,
    started_at: datetime,
    workshop_id: str | None = None,
    seat_number: int | None = None,
    error: str | None = None,
) -> LabSession:
    metadata = {}
    if workshop_id:
        metadata["workshop_id"] = workshop_id
    if seat_number:
        metadata["seat_number"] = seat_number
    lifecycle = [
        LifecycleEvent(
            from_status=SessionStatus.REQUESTED,
            to_status=SessionStatus.PROVISIONING,
            timestamp=started_at,
            reason="provisioning started",
        )
    ]
    if status != SessionStatus.PROVISIONING:
        lifecycle.append(
            LifecycleEvent(
                from_status=SessionStatus.PROVISIONING,
                to_status=status,
                timestamp=started_at + timedelta(seconds=90),
                reason=error or "transition complete",
            )
        )
    return LabSession(
        session_id=session_id,
        request_id=f"request-{session_id}",
        tenant_id="pilot",
        catalog_item_id="agent-lab",
        namespace=f"lab-{session_id}",
        cluster_ref="arena",
        status=status,
        started_at=started_at,
        completed_at=(
            started_at + timedelta(seconds=90)
            if status in {SessionStatus.RECLAIMED, SessionStatus.CLEANUP_FAILED}
            else None
        ),
        lifecycle_events=lifecycle,
        metadata=metadata,
    )


def test_observability_read_model_joins_cluster_lab_and_seat_lifecycle():
    from app.services.admin_observability import build_admin_observability

    now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
    workshop = Workshop(
        workshop_id="workshop-1",
        tenant_id="pilot",
        catalog_item_id="agent-lab",
        num_users=3,
        name="Agent lab rehearsal",
        status=WorkshopStatus.PROVISIONING,
        cluster_ref="arena",
        created_at=now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=4),
        seats=[
            WorkshopSeat(
                workshop_id="workshop-1",
                seat_number=1,
                session_id="seat-1",
                status=WorkshopSeatStatus.READY,
            ),
            WorkshopSeat(
                workshop_id="workshop-1",
                seat_number=2,
                session_id="seat-2",
                status=WorkshopSeatStatus.PROVISIONING,
            ),
            WorkshopSeat(
                workshop_id="workshop-1",
                seat_number=3,
                session_id="seat-3",
                status=WorkshopSeatStatus.FAILED,
                error="Showroom route returned 503",
            ),
        ],
        session_ids=["seat-1", "seat-2", "seat-3"],
    )
    sessions = {
        "seat-1": _session(
            "seat-1",
            status=SessionStatus.READY,
            started_at=now - timedelta(minutes=4),
            workshop_id=workshop.workshop_id,
            seat_number=1,
        ),
        "seat-2": _session(
            "seat-2",
            status=SessionStatus.PROVISIONING,
            started_at=now - timedelta(minutes=3),
            workshop_id=workshop.workshop_id,
            seat_number=2,
        ),
        "seat-3": _session(
            "seat-3",
            status=SessionStatus.CLEANUP_FAILED,
            started_at=now - timedelta(minutes=2),
            workshop_id=workshop.workshop_id,
            seat_number=3,
            error="namespace deletion timed out",
        ),
    }
    clusters = [{
        "cluster_id": "arena",
        "cluster_name": "Arena",
        "healthy": True,
        "eligible": True,
        "reason": "eligible",
        "available_cpu_millicores": 120_000,
        "available_memory_mib": 512_000,
        "available_pods": 250,
        "active_workshops": 1,
        "active_sessions": 3,
        "active_seats": 3,
    }]

    result = build_admin_observability(
        sessions=sessions.values(),
        workshops=[workshop],
        clusters=clusters,
        now=now,
        grafana_url="https://grafana.example/d/launchpad",
        model_inventory={
            "summary": {"configured": 1, "running": 1, "exposed": 1, "healthy": 1},
            "models": [{
                "id": "granite-tools",
                "display_name": "Granite Tools",
                "namespace": "fleet-llm-d",
                "workload": "vllm-granite-tools",
                "hardware": "Intel Xeon",
                "desired_replicas": 2,
                "ready_replicas": 2,
                "litellm_exposed": True,
                "status": "healthy",
            }],
        },
        llm_events=[
            {
                "caller": "seat-1",
                "model": "granite-tools",
                "latency_ms": 1000,
                "tokens_in_est": 20,
                "tokens_out_est": 30,
                "outcome": "success",
            },
            {
                "caller": "lab-seat-3",
                "model": "granite-tools",
                "latency_ms": 2000,
                "tokens_in_est": 10,
                "tokens_out_est": 5,
                "outcome": "rate_limited",
                "status_code": 429,
            },
        ],
    )

    assert result["schema"] == "launchpad.admin-observability/v1"
    assert result["summary"] == {
        "clusters_healthy": 1,
        "clusters_total": 1,
        "labs_active": 1,
        "seats_active": 1,
        "seats_inflight": 1,
        "seats_attention": 1,
    }
    assert result["clusters"][0]["available_cpu_millicores"] == 120_000

    lab = result["provisioning"][0]
    assert lab["order_id"] == "workshop-1"
    assert lab["order_type"] == "workshop"
    assert lab["status_counts"] == {"cleanup_failed": 1, "provisioning": 1, "ready": 1}
    assert lab["ready_seats"] == 1
    assert lab["failed_seats"] == 1
    assert lab["max_ready_seconds"] == 90
    assert [seat["seat_number"] for seat in lab["seats"]] == [1, 2, 3]

    assert result["inflight"][0]["stage_counts"] == {"provisioning": 1}
    assert result["inflight"][0]["oldest_seconds"] == 180
    resolution = result["resolution"][0]
    assert resolution["session_id"] == "seat-3"
    assert resolution["seat_number"] == 3
    assert resolution["state"] == "attention"
    assert resolution["message"] == "Showroom route returned 503"
    assert resolution["detail_url"] == "/sessions/seat-3"
    assert result["grafana"] == {
        "configured": True,
        "url": "https://grafana.example/d/launchpad",
        "purpose": "Historical resource, network, and latency telemetry",
    }
    assert result["llm"]["summary"] == {
        "models_configured": 1,
        "models_running": 1,
        "models_healthy": 1,
        "requests_observed": 2,
        "avg_latency_ms": 1500.0,
        "p95_latency_ms": 2000.0,
        "errors": 1,
        "rate_limited": 1,
        "estimated_tokens": 65,
        "attributed_requests": 2,
    }
    assert result["llm"]["models"][0]["backend"] == (
        "fleet-llm-d/vllm-granite-tools"
    )
    assert result["llm"]["models"][0]["route"] == "LiteLLM: granite-tools"
    assert result["llm"]["attribution"][0]["order_id"] == "workshop-1"
    assert result["llm"]["attribution"][0]["seat_number"] == 1
    assert result["llm"]["telemetry_gaps"] == []


def test_observability_keeps_individual_labs_visible_and_does_not_duplicate_workshop_seats():
    from app.services.admin_observability import build_admin_observability

    now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
    workshop_session = _session(
        "workshop-seat",
        status=SessionStatus.READY,
        started_at=now - timedelta(minutes=2),
        workshop_id="workshop-2",
        seat_number=1,
    )
    individual = _session(
        "individual-1",
        status=SessionStatus.ACTIVE,
        started_at=now - timedelta(minutes=1),
    )
    workshop = Workshop(
        workshop_id="workshop-2",
        tenant_id="pilot",
        catalog_item_id="agent-lab",
        num_users=1,
        status=WorkshopStatus.READY,
        cluster_ref="arena",
        seats=[
            WorkshopSeat(
                workshop_id="workshop-2",
                seat_number=1,
                session_id="workshop-seat",
                status=WorkshopSeatStatus.READY,
            )
        ],
        session_ids=["workshop-seat"],
    )

    result = build_admin_observability(
        sessions=[workshop_session, individual],
        workshops=[workshop],
        clusters=[],
        now=now,
        grafana_url="",
        model_inventory={"summary": {}, "models": []},
        llm_events=[],
    )

    assert [row["order_type"] for row in result["provisioning"]] == [
        "individual",
        "workshop",
    ]
    assert sum(len(row["seats"]) for row in result["provisioning"]) == 2
    assert result["grafana"]["configured"] is False
    assert result["grafana"]["url"] is None
    assert "No LLM request telemetry is currently available" in result["llm"]["telemetry_gaps"]
    assert "LLM endpoint/model inventory is unavailable" in result["llm"]["telemetry_gaps"]


def test_admin_observability_endpoint_is_versioned_and_read_only(monkeypatch):
    from app.api.deps import provisioning_service
    from app.api.routers import admin
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(provisioning_service, "_sessions", {})
    monkeypatch.setattr(provisioning_service, "_workshops", {})
    monkeypatch.setattr(
        provisioning_service,
        "get_cluster_fleet_health",
        lambda: [{"cluster_id": "arena", "healthy": True}],
    )
    monkeypatch.setattr(
        admin,
        "get_model_inventory",
        lambda: {"summary": {"configured": 0}, "models": []},
    )
    monkeypatch.setattr(admin, "get_llm_audit_log", list)
    monkeypatch.setenv("GRAFANA_LAUNCHPAD_DASHBOARD_URL", "https://grafana.example/d/fleet")

    response = TestClient(app).get("/api/v1/admin/observability")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "launchpad.admin-observability/v1"
    assert payload["clusters"] == [{"cluster_id": "arena", "healthy": True}]
    assert payload["grafana"]["url"] == "https://grafana.example/d/fleet"
    assert provisioning_service._sessions == {}
    assert provisioning_service._workshops == {}


def test_admin_observability_openapi_contract_names_all_operator_angles():
    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts/admin-observability-v1.yaml").read_text()
    )

    operation = contract["paths"]["/api/v1/admin/observability"]["get"]
    assert operation["security"] == [{"openshiftAdmin": []}]
    required = set(
        contract["components"]["schemas"]["AdminObservability"]["required"]
    )
    assert {
        "clusters",
        "provisioning",
        "inflight",
        "resolution",
        "llm",
        "grafana",
    } <= required
