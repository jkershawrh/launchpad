"""
API endpoints for the Inference Gateway

Provides queryable history of routing decisions, governance audit trail,
backend management, and cost analytics. All data served from PostgreSQL.
Returns 503 when DB is unavailable.
"""

import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

import db

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api/v1", tags=["api"])


class ApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=100)


async def _require_db():
    if not await db.is_connected():
        raise HTTPException(503, "Database not connected")


@api_router.get("/requests")
async def list_requests(
    task: Optional[str] = None,
    backend: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    """Query inference request history with optional filters"""
    await _require_db()
    offset = (page - 1) * per_page
    rows = await db.get_requests(task=task, backend=backend, status=status,
                                  limit=per_page, offset=offset)
    return {"data": rows, "page": page, "per_page": per_page}


@api_router.get("/requests/{request_id}")
async def get_request(request_id: UUID):
    """Get a single inference request by ID"""
    await _require_db()
    row = await db.get_request_by_id(str(request_id))
    if not row:
        raise HTTPException(404, f"Request {request_id} not found")
    return row


@api_router.get("/decisions")
async def list_decisions(
    decision: Optional[str] = None,
    source: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    """Query governance decisions with optional filters"""
    await _require_db()
    offset = (page - 1) * per_page
    rows = await db.get_decisions(decision=decision, source=source,
                                   limit=per_page, offset=offset)
    return {"data": rows, "page": page, "per_page": per_page}


@api_router.get("/decisions/{decision_id}")
async def get_decision(decision_id: UUID):
    """Get a single governance decision with evidence bundle"""
    await _require_db()
    row = await db.get_decision_by_id(str(decision_id))
    if not row:
        raise HTTPException(404, f"Decision {decision_id} not found")
    return row


@api_router.post("/decisions/{decision_id}/approve")
async def approve_decision(
    decision_id: UUID,
    body: ApproveRequest,
):
    """Record human approval for a governance decision"""
    await _require_db()
    success = await db.approve_decision(str(decision_id), body.approved_by)
    if not success:
        raise HTTPException(404, f"Decision {decision_id} not found or approval failed")
    return {"status": "approved", "decision_id": str(decision_id), "approved_by": body.approved_by}


@api_router.get("/backends")
async def list_backends_api():
    """List all registered backends with status"""
    await _require_db()
    rows = await db.get_backends_from_db()
    return {"data": rows}


@api_router.get("/routing-rules")
async def list_routing_rules():
    """List active routing rules"""
    await _require_db()
    rows = await db.get_routing_rules()
    return {"data": rows}


@api_router.get("/cost-summary")
async def cost_summary(days: int = Query(default=30, ge=1, le=365)):
    """Cost breakdown by backend and task type"""
    await _require_db()
    rows = await db.get_cost_summary(days=days)
    return {"data": rows, "period_days": days}


@api_router.get("/analytics/routing-distribution")
async def routing_distribution(days: int = Query(default=7, ge=1, le=90)):
    """Percentage of requests routed to each backend"""
    await _require_db()
    rows = await db.get_routing_distribution(days=days)
    return {"data": rows, "period_days": days}


@api_router.get("/analytics/latency-percentiles")
async def latency_percentiles(days: int = Query(default=7, ge=1, le=90)):
    """Latency percentiles (p50, p95, p99) by backend"""
    await _require_db()
    rows = await db.get_latency_percentiles(days=days)
    return {"data": rows, "period_days": days}


@api_router.get("/analytics/cost-by-task")
async def cost_by_task(days: int = Query(default=30, ge=1, le=365)):
    """Cost breakdown by task type"""
    await _require_db()
    rows = await db.get_cost_by_task(days=days)
    return {"data": rows, "period_days": days}


@api_router.get("/analytics/governance-summary")
async def governance_summary(days: int = Query(default=30, ge=1, le=365)):
    """Summary of governance decisions: approved, denied, escalated"""
    await _require_db()
    rows = await db.get_governance_summary(days=days)
    return {"data": rows, "period_days": days}
