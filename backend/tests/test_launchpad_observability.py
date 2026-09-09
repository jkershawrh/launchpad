"""Contracts for the Launchpad operational telemetry package."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from app.domain.enums import SessionStatus, WorkshopSeatStatus, WorkshopStatus
from app.domain.lifecycle_jobs import (
    LifecycleJob,
    LifecycleJobOperation,
    LifecycleJobStatus,
)
from app.domain.models import LabSession, LifecycleEvent, Workshop, WorkshopSeat
from app.services.observability_metrics import render_launchpad_metrics
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY = ROOT / "deploy/launchpad/observability"


def _documents(name: str) -> list[dict]:
    return [
        document for document in yaml.safe_load_all((OBSERVABILITY / name).read_text()) if document
    ]


def test_metrics_describe_workshop_seats_inflight_and_resolution_without_identity_data():
    started = datetime(2026, 9, 8, 0, 0, 0, tzinfo=UTC)
    ready = started + timedelta(seconds=47)
    reclaimed = ready + timedelta(seconds=180)
    session = LabSession(
        session_id="session-safe",
        request_id="request-safe",
        tenant_id="tenant-must-not-leak",
        catalog_item_id="serve-llms",
        cluster_ref="arena",
        status=SessionStatus.RECLAIMED,
        completed_at=reclaimed,
        lifecycle_events=[
            LifecycleEvent(
                from_status=SessionStatus.REQUESTED,
                to_status=SessionStatus.PROVISIONING,
                timestamp=started,
            ),
            LifecycleEvent(
                from_status=SessionStatus.PROVISIONING,
                to_status=SessionStatus.VALIDATING,
                timestamp=started + timedelta(seconds=40),
            ),
            LifecycleEvent(
                from_status=SessionStatus.VALIDATING,
                to_status=SessionStatus.READY,
                timestamp=ready,
            ),
            LifecycleEvent(
                from_status=SessionStatus.READY,
                to_status=SessionStatus.RESETTING,
                timestamp=ready + timedelta(seconds=170),
            ),
            LifecycleEvent(
                from_status=SessionStatus.RESETTING,
                to_status=SessionStatus.RECLAIMED,
                timestamp=reclaimed,
            ),
        ],
        metadata={"workshop_id": "workshop-safe", "seat_number": 1},
    )
    workshop = Workshop(
        workshop_id="workshop-safe",
        tenant_id="tenant-must-not-leak",
        catalog_item_id="serve-llms",
        num_users=1,
        cluster_ref="arena",
        status=WorkshopStatus.COMPLETED,
        seats=[
            WorkshopSeat(
                workshop_id="workshop-safe",
                seat_number=1,
                participant_id="participant-must-not-leak",
                session_id="session-safe",
                status=WorkshopSeatStatus.RECLAIMED,
            )
        ],
    )

    body = render_launchpad_metrics(
        sessions=[session],
        workshops=[workshop],
        cluster_targets=[],
        now=reclaimed,
    ).decode()

    assert (
        'launchpad_workshop_seats{catalog_item="serve-llms",cluster="arena",status="reclaimed"} 1'
        in body
    )
    assert (
        'launchpad_session_provision_duration_seconds_sum{catalog_item="serve-llms",cluster="arena",outcome="ready"} 47'
        in body
    )
    assert (
        'launchpad_session_resolution_duration_seconds_sum{catalog_item="serve-llms",cluster="arena",outcome="reclaimed"} 10'
        in body
    )
    assert "tenant-must-not-leak" not in body
    assert "participant-must-not-leak" not in body
    assert "request-safe" not in body
    assert "session-safe" not in body
    assert "workshop-safe" not in body


def test_metrics_report_lifecycle_queue_age_leases_and_takeovers_without_ids():
    now = datetime(2026, 9, 8, 12, 5, 0, tzinfo=UTC)
    queued = LifecycleJob(
        job_id="job-must-not-leak",
        operation=LifecycleJobOperation.RECLAIM_WORKSHOP,
        aggregate_type="workshop",
        aggregate_id="workshop-must-not-leak",
        cluster_ref="arena",
        idempotency_key="idempotency-must-not-leak",
        created_at=now - timedelta(seconds=90),
        updated_at=now - timedelta(seconds=90),
        next_attempt_at=now - timedelta(seconds=90),
    )
    running = LifecycleJob(
        operation=LifecycleJobOperation.PROVISION_WORKSHOP,
        aggregate_type="workshop",
        aggregate_id="workshop-two",
        cluster_ref="brutus",
        idempotency_key="workshop:two:provision:v1",
        status=LifecycleJobStatus.RUNNING,
        attempts=3,
        fencing_token=3,
        lease_until=now + timedelta(seconds=15),
        created_at=now - timedelta(seconds=120),
        updated_at=now,
        next_attempt_at=now - timedelta(seconds=120),
    )

    body = render_launchpad_metrics(
        sessions=[],
        workshops=[],
        cluster_targets=[],
        lifecycle_jobs=[queued, running],
        now=now,
    ).decode()

    assert (
        'launchpad_lifecycle_jobs{cluster="arena",operation="reclaim_workshop",status="queued"} 1'
        in body
    )
    assert (
        'launchpad_lifecycle_job_age_seconds_max{cluster="arena",operation="reclaim_workshop",status="queued"} 90'
        in body
    )
    assert (
        'launchpad_lifecycle_lease_seconds_remaining{cluster="brutus",operation="provision_workshop"} 15'
        in body
    )
    assert (
        'launchpad_lifecycle_takeovers_total{cluster="brutus",operation="provision_workshop"} 2'
        in body
    )
    assert "job-must-not-leak" not in body
    assert "workshop-must-not-leak" not in body
    assert "idempotency-must-not-leak" not in body


def test_metrics_endpoint_is_prometheus_text_and_not_buried_under_admin_auth():
    from app.main import app

    response = TestClient(app).get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "launchpad_sessions" in response.text


def test_observability_package_scrapes_backend_and_supplies_recording_rules():
    kustomization = yaml.safe_load((OBSERVABILITY / "kustomization.yaml").read_text())
    assert {"service-monitor.yaml", "prometheus-rules.yaml"} <= set(kustomization["resources"])

    monitor = _documents("service-monitor.yaml")[0]
    assert monitor["kind"] == "ServiceMonitor"
    assert monitor["spec"]["selector"]["matchLabels"]["app.kubernetes.io/name"] == "backend"
    endpoint = monitor["spec"]["endpoints"][0]
    assert endpoint == {
        "port": "http",
        "path": "/metrics",
        "interval": "30s",
        "scrapeTimeout": "10s",
    }

    rule = _documents("prometheus-rules.yaml")[0]
    record_rules = {
        item["record"]: item
        for group in rule["spec"]["groups"]
        for item in group["rules"]
        if item.get("record")
    }
    expressions = {
        item.get("record") or item.get("alert"): item["expr"]
        for group in rule["spec"]["groups"]
        for item in group["rules"]
    }
    assert {
        "launchpad:cluster:cpu_headroom_ratio",
        "launchpad:cluster:memory_headroom_ratio",
        "launchpad:cluster:pod_slot_headroom_ratio",
        "launchpad:workshop:inflight_seats",
        "LaunchpadSeatProvisioningStalled",
        "LaunchpadSeatReclaimStalled",
        "LaunchpadCleanupFailed",
        "LaunchpadLifecycleJobStalled",
        "LaunchpadLifecycleJobFailed",
        "LaunchpadReclaimJobStalled",
    } <= set(expressions)
    for name in (
        "launchpad:cluster:cpu_headroom_ratio",
        "launchpad:cluster:memory_headroom_ratio",
        "launchpad:cluster:pod_slot_headroom_ratio",
    ):
        assert record_rules[name]["labels"]["cluster"] == "arena"


def test_grafana_dashboard_covers_the_four_operational_views():
    dashboard = json.loads((OBSERVABILITY / "launchpad-operations.json").read_text())
    assert dashboard["title"] == "Launchpad Workshop Operations"
    assert dashboard["uid"] == "launchpad-workshop-operations"
    row_titles = {panel["title"] for panel in dashboard["panels"] if panel["type"] == "row"}
    assert row_titles == {
        "1. Cluster health and capacity",
        "2. Provisioning by lab and seat",
        "3. In-flight work by lab and seat",
        "4. Resolution, reclaim, and cleanup",
        "5. LLM serving and usage",
    }
    expressions = [
        target["expr"] for panel in dashboard["panels"] for target in panel.get("targets", [])
    ]
    assert any("launchpad_workshop_seats" in expression for expression in expressions)
    assert any(
        "launchpad_session_provision_duration_seconds" in expression for expression in expressions
    )
    assert any(
        "launchpad_session_state_age_seconds_max" in expression for expression in expressions
    )
    assert any(
        "launchpad_session_resolution_duration_seconds" in expression for expression in expressions
    )
    assert any("gateway_requests_total" in expression for expression in expressions)
    assert any("vllm:num_requests_running" in expression for expression in expressions)


def test_arena_overlay_enables_the_reusable_observability_package():
    overlay = yaml.safe_load(
        (ROOT / "deploy/launchpad/overlays/arena/kustomization.yaml").read_text()
    )
    assert "../../observability" in overlay["resources"]


def test_arena_models_are_discoverable_without_exposing_model_metrics_publicly():
    model_dir = ROOT / "deploy/models/arena"
    kustomization = yaml.safe_load((model_dir / "kustomization.yaml").read_text())
    assert "model-observability.yaml" in kustomization["resources"]
    documents = [
        item
        for item in yaml.safe_load_all((model_dir / "model-observability.yaml").read_text())
        if item
    ]
    monitors = {item["metadata"]["name"]: item for item in documents}
    assert set(monitors) == {"vllm-granite-tools", "tei-nomic-embed"}
    for monitor in monitors.values():
        assert monitor["kind"] == "ServiceMonitor"
        assert monitor["metadata"]["namespace"] == "fleet-llm-d"
        assert monitor["spec"]["endpoints"][0]["path"] == "/metrics"
        assert "namespaceSelector" not in monitor["spec"]


def test_arena_model_network_policies_admit_user_workload_prometheus():
    model_dir = ROOT / "deploy/models/arena"
    policies = []
    for name in ("granite-3.2-8b-tools.yaml", "nomic-embed-text-v1.5.yaml"):
        policies.extend(
            item
            for item in yaml.safe_load_all((model_dir / name).read_text())
            if item and item.get("kind") == "NetworkPolicy"
        )

    monitored = {
        "allow-launchpad-to-granite-tools",
        "allow-launchpad-to-nomic-embed",
    }
    for policy in policies:
        if policy["metadata"]["name"] not in monitored:
            continue
        control_plane_sources = [
            source
            for ingress in policy["spec"]["ingress"]
            for source in ingress.get("from", [])
            if source.get("namespaceSelector", {}).get("matchLabels", {}).get(
                "kubernetes.io/metadata.name"
            )
            == "partner-ai-launchpad"
        ]
        assert len(control_plane_sources) == 1
        assert control_plane_sources[0]["podSelector"]["matchExpressions"] == [
            {
                "key": "app.kubernetes.io/name",
                "operator": "In",
                "values": ["backend", "lifecycle-worker"],
            }
        ]
        namespaces = {
            source.get("namespaceSelector", {}).get("matchLabels", {}).get(
                "kubernetes.io/metadata.name"
            )
            for ingress in policy["spec"]["ingress"]
            for source in ingress.get("from", [])
        }
        assert "openshift-user-workload-monitoring" in namespaces


def test_observability_decision_records_available_llm_signals_and_gaps():
    content = (ROOT / "docs/observability-architecture.md").read_text()
    for phrase in (
        "vLLM",
        "Text Embeddings Inference",
        "request and error counts",
        "input and output token totals",
        "rate-limit rejections",
        "Per-seat inference attribution",
        "No secrets",
        "not install a second metrics stack",
    ):
        assert phrase in content


def test_arena_readonly_observability_evidence_is_explicitly_not_live_certification():
    receipt = ROOT / "evidence/arena-observability-readonly-2026-09-08.json"
    evidence = json.loads(receipt.read_text())
    assert evidence["mutation_performed"] is False
    assert evidence["cluster_access"] == {
        "cluster": "arena",
        "explicit_kubeconfig_required": True,
        "default_context_changed": False,
    }
    assert evidence["user_workload_monitoring"]["prometheus_user_workload_replicas_ready"] == "2/2"
    assert evidence["model_serving"]["vllm_granite_3_2_8b_tools"]["ready_replicas"] == 2
    assert evidence["model_serving"]["tei_nomic_embed"] == {
        "desired_replicas": 1,
        "ready_replicas": 1,
        "metrics_endpoint_reachable": True,
        "metrics_available": False,
        "prometheus_body_bytes": 0,
        "reason": "A read-only port-forward returned HTTP 200 from /metrics with an empty body; TEI metrics are not available from this installed build/configuration.",
    }
    assert evidence["repository_candidate"]["live_deployment"] == "NOT_RUN"
    assert evidence["result"] == "PARTIAL"
    assert evidence["sensitive_output"]["secrets_present"] is False
    checksum = (
        (ROOT / "evidence/arena-observability-readonly-2026-09-08.json.sha256")
        .read_text()
        .split()[0]
    )
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == checksum
