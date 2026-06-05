from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import get_placement_service, get_feedback_tracker, get_deepfield_adapter, get_brain, get_fleet_enrichment, provisioning_service

router = APIRouter(tags=["intelligence"])


@router.get("/intelligence/fleet-health")
def fleet_health() -> Dict[str, Any]:
    clusters = []
    placement = get_placement_service()
    if placement:
        if not placement.get_capacity_snapshot():
            placement.refresh_capacity_cache()
        clusters = [c.model_dump() for c in placement.get_capacity_snapshot()]

    alerts = []
    brain = get_brain()
    if brain:
        try:
            health_alerts = brain.proactive_health_check()
            alerts = [a.model_dump() for a in health_alerts]
        except Exception:
            pass

    return {"clusters": clusters, "alerts": alerts}


@router.get("/intelligence/decision/{request_id}")
def get_decision(request_id: str) -> Dict[str, Any]:
    for session in provisioning_service._sessions.values():
        if session.request_id == request_id:
            decision_data = session.resources.get("decision")
            if decision_data:
                return decision_data
            raise HTTPException(404, "No decision recorded for this request")
    raise HTTPException(404, f"No session found for request {request_id}")


class SimulateRequest(BaseModel):
    catalog_item_id: str
    hardware_profile: Optional[str] = None
    tenant_id: str = "simulate"


@router.post("/intelligence/simulate")
def simulate_placement(body: SimulateRequest) -> Dict[str, Any]:
    brain = get_brain()
    if not brain:
        raise HTTPException(503, "Orchestration brain not configured")

    from app.domain.enums import CatalogCategory
    from app.domain.models import LabRequest
    catalog_item = provisioning_service.catalog.get_item(body.catalog_item_id)
    if not catalog_item:
        raise HTTPException(404, f"Catalog item {body.catalog_item_id} not found")

    request = LabRequest(
        tenant_id=body.tenant_id,
        requester_id="simulate",
        catalog_item_id=body.catalog_item_id,
        requested_mode=CatalogCategory.QUICK_START,
        hardware_profile=body.hardware_profile,
    )

    decision = brain.decide(request, catalog_item)
    result = decision.model_dump()

    if brain.classifier and decision.workload_profile:
        try:
            matches = brain.classifier.match_hardware(decision.workload_profile)
            result["hardware_matches"] = [m.model_dump() for m in matches[:5]]
        except Exception:
            result["hardware_matches"] = []
    else:
        result["hardware_matches"] = []

    return result


@router.get("/intelligence/cluster/{cluster_name}/signals")
def cluster_signals(cluster_name: str) -> Dict[str, Any]:
    deepfield = get_deepfield_adapter()
    if not deepfield:
        return {"cluster_name": cluster_name, "signals": []}

    signals = deepfield.get_cluster_signals(cluster_name)
    return {
        "cluster_name": cluster_name,
        "signals": [s.model_dump() for s in signals],
    }


@router.get("/admin/feedback/summary")
def feedback_summary() -> Dict[str, Any]:
    tracker = get_feedback_tracker()
    if not tracker:
        return {"summaries": []}

    all_outcomes = tracker.get_outcomes()
    seen = set()
    summaries = []
    for o in all_outcomes:
        key = (o.catalog_item_id, o.cluster_name or "", o.hardware_profile)
        if key in seen:
            continue
        seen.add(key)
        s = tracker.get_summary(o.catalog_item_id, o.cluster_name or "", o.hardware_profile)
        if s:
            summaries.append(s.model_dump())

    return {"summaries": summaries}


@router.get("/admin/feedback/cluster/{cluster_name}")
def feedback_by_cluster(cluster_name: str) -> Dict[str, Any]:
    tracker = get_feedback_tracker()
    if not tracker:
        return {"summaries": []}

    outcomes = tracker.get_outcomes(cluster_name=cluster_name)
    seen = set()
    summaries = []
    for o in outcomes:
        key = (o.catalog_item_id, o.hardware_profile)
        if key in seen:
            continue
        seen.add(key)
        s = tracker.get_summary(o.catalog_item_id, cluster_name, o.hardware_profile)
        if s:
            summaries.append(s.model_dump())

    return {"summaries": summaries}


@router.get("/admin/feedback/catalog/{catalog_item_id}")
def feedback_by_catalog(catalog_item_id: str) -> Dict[str, Any]:
    tracker = get_feedback_tracker()
    if not tracker:
        return {"summaries": []}

    outcomes = tracker.get_outcomes(catalog_item_id=catalog_item_id)
    seen = set()
    summaries = []
    for o in outcomes:
        key = (o.cluster_name or "", o.hardware_profile)
        if key in seen:
            continue
        seen.add(key)
        s = tracker.get_summary(catalog_item_id, o.cluster_name or "", o.hardware_profile)
        if s:
            summaries.append(s.model_dump())

    return {"summaries": summaries}


@router.get("/admin/feedback/outcomes")
def feedback_outcomes(
    catalog_item_id: Optional[str] = None,
    cluster_name: Optional[str] = None,
) -> Dict[str, Any]:
    tracker = get_feedback_tracker()
    if not tracker:
        return {"outcomes": []}

    outcomes = tracker.get_outcomes(
        catalog_item_id=catalog_item_id,
        cluster_name=cluster_name,
    )
    return {"outcomes": [o.model_dump() for o in outcomes[:100]]}


@router.post("/intelligence/seed")
def seed_from_babylon() -> Dict[str, Any]:
    import os
    kubeconfig = os.environ.get("BABYLON_KUBECONFIG", "")
    if not kubeconfig:
        raise HTTPException(503, "BABYLON_KUBECONFIG not configured")

    from app.services.data_seeder import DataSeeder
    seeder = DataSeeder(kubeconfig_path=kubeconfig)
    result = seeder.seed_from_babylon()

    if "error" in result:
        raise HTTPException(500, result["error"])

    tracker = get_feedback_tracker()
    seeded = 0
    if tracker:
        for outcome in seeder.get_provisioning_outcomes():
            tracker.record_outcome(outcome)
            seeded += 1

    outcomes = result.get("outcomes", [])
    event_outcomes = [o for o in outcomes if o.get("stage") == "event"]
    prod_outcomes = [o for o in outcomes if o.get("stage") == "prod"]

    return {
        "seeded": seeded,
        "total_subjects": result.get("total_subjects", 0),
        "breakdown": {
            "prod": len(prod_outcomes),
            "event": len(event_outcomes),
            "dev": result.get("dev", 0),
        },
        "success_rate": round(result.get("success", 0) / max(1, result.get("total_outcomes", 1)) * 100, 1),
        "catalog_items": result.get("catalog_items", 0),
        "event_catalog_items": list(set(o["catalog_item"] for o in event_outcomes)),
    }


_classification_cache: Dict[str, Any] = {}
_classification_cache_time: float = 0


@router.get("/intelligence/classifications")
def batch_classifications() -> Dict[str, Any]:
    import time
    global _classification_cache, _classification_cache_time

    if _classification_cache and time.time() - _classification_cache_time < 300:
        return _classification_cache

    brain = get_brain()
    classifier = brain.classifier if brain else None
    if not classifier:
        return {"items": [], "classified": 0, "total": 0}

    from app.domain.enums import CatalogCategory
    from app.domain.models import LabRequest

    catalog_items = provisioning_service.catalog.list_items()
    results = []

    for item in catalog_items:
        try:
            profile = classifier.classify(item, LabRequest(
                tenant_id="classify", requester_id="batch",
                catalog_item_id=item.catalog_item_id,
                requested_mode=CatalogCategory.QUICK_START,
            ))
            matches = classifier.match_hardware(profile)
            results.append({
                "catalog_item_id": item.catalog_item_id,
                "display_name": item.display_name,
                "description": item.description[:200] if item.description else "",
                "category": item.category.value if hasattr(item.category, 'value') else str(item.category),
                "workload_profile": profile.model_dump(),
                "recommended_hardware": matches[0].hardware_profile if matches else "unknown",
                "recommended_quota": matches[0].right_sized_quota if matches else "standard",
                "hardware_matches": [m.model_dump() for m in matches[:5]],
            })
        except Exception:
            results.append({
                "catalog_item_id": item.catalog_item_id,
                "display_name": item.display_name,
                "description": item.description[:200] if item.description else "",
                "category": item.category.value if hasattr(item.category, 'value') else str(item.category),
                "workload_profile": None,
                "recommended_hardware": item.default_hardware_profile or "unknown",
                "recommended_quota": item.default_quota_profile or "standard",
                "hardware_matches": [],
            })

    classified = len([r for r in results if r["workload_profile"]])
    _classification_cache = {"items": results, "classified": classified, "total": len(results)}
    _classification_cache_time = time.time()
    return _classification_cache


@router.get("/intelligence/enrichment")
def fleet_enrichment_data() -> Dict[str, Any]:
    enrichment = get_fleet_enrichment()
    if not enrichment:
        return {"summary": {}, "failure_classes": {}, "clusters": {}, "incidents": [], "signals": []}

    if enrichment.is_stale():
        enrichment.refresh()

    return {
        "summary": enrichment.get_summary(),
        "failure_classes": enrichment.get_failure_classes(),
        "clusters": enrichment.get_cluster_observatory(),
        "incidents": enrichment.get_incidents(),
        "signals": enrichment.get_signals(),
        "provisioning": enrichment.get_provisioning_stats(),
        "pools": enrichment.get_pool_summary()[:20],
    }


_timing_service = None


def _get_timing():
    global _timing_service
    if _timing_service is None:
        import os
        kc = os.environ.get("BABYLON_KUBECONFIG", "")
        if kc:
            from app.services.provisioning_timing import ProvisioningTiming
            _timing_service = ProvisioningTiming(kubeconfig_path=kc)
    return _timing_service


@router.get("/intelligence/timing")
def provisioning_timing() -> Dict[str, Any]:
    svc = _get_timing()
    if not svc:
        return {"stats": {}, "recent": []}

    if svc.is_stale():
        svc.refresh()

    stats = svc.get_stats()
    recent = svc.get_all()[-20:]

    return {
        "stats": stats,
        "recent": recent,
    }


@router.get("/intelligence/timing/catalog/{catalog_item_id}")
def timing_by_catalog(catalog_item_id: str) -> Dict[str, Any]:
    svc = _get_timing()
    if not svc:
        return {"provisions": []}

    if svc.is_stale():
        svc.refresh()

    provisions = [t for t in svc.get_all() if t["catalog_item"] == catalog_item_id]
    provisions.sort(key=lambda t: t["created"], reverse=True)

    durations = [t["duration_seconds"] for t in provisions]
    stats = {}
    if durations:
        durations_sorted = sorted(durations)
        n = len(durations_sorted)
        stats = {
            "count": n,
            "avg_minutes": round(sum(durations) / n / 60, 1),
            "median_minutes": round(durations_sorted[n // 2] / 60, 1),
            "min_minutes": round(durations_sorted[0] / 60, 1),
            "max_minutes": round(durations_sorted[-1] / 60, 1),
        }

    return {"catalog_item": catalog_item_id, "stats": stats, "provisions": provisions[:50]}
