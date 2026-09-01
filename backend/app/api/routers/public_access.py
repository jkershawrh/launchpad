from __future__ import annotations

import os

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import public_access_service
from app.auth.oauth import User, require_admin

router = APIRouter(prefix="/public-access", tags=["public-access"])


class ClaimRequest(BaseModel):
    order_id: str
    email: str
    code: str


def _owner_summary(order_id: str) -> dict:
    policy = public_access_service.get_policy(order_id)
    if not policy:
        raise HTTPException(404, "Public access policy not found")
    entitlements = [e for e in public_access_service._entitlements.values() if e.order_id == order_id]
    return {
        "order_id": order_id,
        "public_url": policy.public_url,
        "enabled": policy.enabled,
        "expires_at": policy.expires_at,
        "seat_limit": policy.seat_limit,
        "claim_count": len(entitlements),
        "code_version": policy.code_version,
    }


@router.get("/orders/{order_id}")
def public_order(order_id: str):
    summary = _owner_summary(order_id)
    return {key: summary[key] for key in ("order_id", "enabled", "expires_at", "seat_limit", "claim_count")}


@router.post("/claim")
def claim(body: ClaimRequest, request: Request, response: Response):
    try:
        result = public_access_service.claim(
            body.order_id, body.email, body.code,
            request.client.host if request.client else "unknown",
        )
    except ValueError as exc:
        raise HTTPException(403, str(exc))
    response.set_cookie(
        "launchpad_access", result.session_token, httponly=True, secure=True,
        samesite="lax", path="/", max_age=300,
    )
    return {
        "order_id": body.order_id,
        "seat_ref": result.entitlement.seat_ref,
        "public_url": result.public_url,
        "participant_id": result.identity.participant_id,
    }


@router.get("/authorize/{order_id}")
def authorize(order_id: str, launchpad_access: str | None = Cookie(default=None)):
    try:
        session = public_access_service.validate_session(launchpad_access or "", order_id)
        entitlement = public_access_service._entitlements[(order_id, session.participant_id)]
        return {"authorized": True, "participant_id": session.participant_id, "seat_ref": entitlement.seat_ref}
    except ValueError:
        raise HTTPException(403, "Access denied")


@router.get("/admin/orders/{order_id}")
def owner_status(order_id: str, _user: User = Depends(require_admin)):
    return _owner_summary(order_id)


@router.post("/admin/orders/{order_id}/rotate")
def rotate(order_id: str, _user: User = Depends(require_admin)):
    try:
        return {"one_time_access_code": public_access_service.rotate_code(order_id), **_owner_summary(order_id)}
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/admin/orders/{order_id}/participants/{participant_id}", status_code=204)
def remove_participant(order_id: str, participant_id: str, _user: User = Depends(require_admin)):
    try:
        public_access_service.remove_participant(order_id, participant_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/private/validate")
def keycloak_validate(body: ClaimRequest, request: Request, x_access_broker_key: str = Header(default="")):
    expected = os.getenv("ACCESS_BROKER_KEY", "")
    if not expected or not __import__("secrets").compare_digest(expected, x_access_broker_key):
        raise HTTPException(403, "Forbidden")
    try:
        result = public_access_service.claim(body.order_id, body.email, body.code, request.client.host if request.client else "keycloak")
        return {
            "active": True,
            "subject": result.identity.participant_id,
            "preferred_username": result.identity.keycloak_username,
            "seat_ref": result.entitlement.seat_ref,
            "expires_at": result.entitlement.expires_at,
        }
    except ValueError:
        raise HTTPException(403, "Access request cannot be completed")
