from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import provisioning_service, public_access_service
from app.auth.oauth import User, require_admin

router = APIRouter(prefix="/public-access", tags=["public-access"])


class ClaimRequest(BaseModel):
    order_id: str
    email: str
    code: str


def _require_broker(key: str) -> None:
    expected = os.getenv("ACCESS_BROKER_KEY", "")
    if not expected or not __import__("secrets").compare_digest(expected, key):
        raise HTTPException(403, "Forbidden")


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
    try:
        provisioning_service.bind_public_participant(
            body.order_id, result.entitlement.seat_ref, result.identity.keycloak_username
        )
    except ValueError as exc:
        public_access_service.remove_participant(body.order_id, result.identity.participant_id)
        raise HTTPException(503, "Claimed environment is not ready") from exc
    response.set_cookie(
        "launchpad_access", result.session_token, httponly=True, secure=True,
        samesite="lax", path="/",
        max_age=max(1, int((result.session_expires_at - datetime.utcnow()).total_seconds())),
    )
    return {
        "order_id": body.order_id,
        "seat_ref": result.entitlement.seat_ref,
        "public_url": result.public_url,
        "participant_id": result.identity.participant_id,
        "session_expires_at": result.session_expires_at,
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
        for entitlement in public_access_service._entitlements.values():
            if entitlement.order_id == order_id and entitlement.status.value == "active":
                identity = next((item for item in public_access_service._identities.values() if item.participant_id == entitlement.participant_id), None)
                if identity:
                    provisioning_service.unbind_public_participant(order_id, entitlement.seat_ref, identity.keycloak_username)
        return {"one_time_access_code": public_access_service.rotate_code(order_id), **_owner_summary(order_id)}
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/admin/orders/{order_id}/participants/{participant_id}", status_code=204)
def remove_participant(order_id: str, participant_id: str, _user: User = Depends(require_admin)):
    try:
        entitlement = public_access_service._entitlements.get((order_id, participant_id))
        identity = next((item for item in public_access_service._identities.values() if item.participant_id == participant_id), None)
        if entitlement and identity:
            provisioning_service.unbind_public_participant(order_id, entitlement.seat_ref, identity.keycloak_username)
        public_access_service.remove_participant(order_id, participant_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/private/validate")
def keycloak_validate(body: ClaimRequest, request: Request, x_access_broker_key: str = Header(default="")):
    _require_broker(x_access_broker_key)
    try:
        result = public_access_service.claim(body.order_id, body.email, body.code, request.client.host if request.client else "keycloak")
        provisioning_service.bind_public_participant(
            body.order_id, result.entitlement.seat_ref, result.identity.keycloak_username
        )
        return {
            "active": True,
            "subject": result.identity.participant_id,
            "preferred_username": result.identity.keycloak_username,
            "seat_ref": result.entitlement.seat_ref,
            "expires_at": result.entitlement.expires_at,
        }
    except ValueError:
        raise HTTPException(403, "Access request cannot be completed")


@router.get("/private/resolve")
def resolve_gateway_target(
    host: str,
    launchpad_access: str | None = Cookie(default=None),
    x_access_broker_key: str = Header(default=""),
):
    _require_broker(x_access_broker_key)
    policy = public_access_service.get_policy_by_host(host)
    if not policy:
        raise HTTPException(404, "Public order not found")
    try:
        session = public_access_service.validate_session(launchpad_access or "", policy.order_id)
    except ValueError:
        raise HTTPException(403, "Access denied")
    entitlement = public_access_service._entitlements[(policy.order_id, session.participant_id)]
    showroom_url = workspace_url = console_url = None
    if policy.order_type == "workshop":
        workshop = provisioning_service.get_workshop(policy.order_id)
        seat = next((item for item in (workshop.seats if workshop else []) if item.seat_id == entitlement.seat_ref), None)
        if seat:
            showroom_url = seat.showroom_url
            workspace_url = seat.lab_url
            lab_session = provisioning_service._sessions.get(seat.session_id or "")
        else:
            lab_session = None
    else:
        lab_session = next((item for item in provisioning_service._sessions.values() if item.request_id == policy.order_id), None)
        if lab_session:
            showroom_url = lab_session.lab_url
            workspace_url = lab_session.dashboard_url or lab_session.lab_url
    if lab_session and lab_session.cluster_ref and provisioning_service.cluster_registry:
        target = provisioning_service.cluster_registry.get(lab_session.cluster_ref)
        console_url = target.public_console_url or target.console_url
    return {
        "order_id": policy.order_id,
        "seat_ref": entitlement.seat_ref,
        "expires_at": entitlement.expires_at,
        "showroom_url": showroom_url,
        "workspace_url": workspace_url,
        "console_url": console_url,
    }


@router.get("/private/order-by-host")
def order_by_host(host: str, x_access_broker_key: str = Header(default="")):
    _require_broker(x_access_broker_key)
    policy = public_access_service.get_policy_by_host(host)
    if not policy or not policy.enabled:
        raise HTTPException(404, "Public order not found")
    return {"order_id": policy.order_id, "expires_at": policy.expires_at}


@router.get("/private/resolve-identity")
def resolve_oidc_identity(host: str, username: str, x_access_broker_key: str = Header(default="")):
    _require_broker(x_access_broker_key)
    policy = public_access_service.get_policy_by_host(host)
    identity = next((item for item in public_access_service._identities.values() if item.keycloak_username == username), None)
    if not policy or not policy.enabled or not identity or identity.disabled_at:
        raise HTTPException(403, "Access denied")
    entitlement = public_access_service._entitlements.get((policy.order_id, identity.participant_id))
    if not entitlement:
        raise HTTPException(403, "Access denied")
    # Reuse the target resolver's mapping without trusting a browser-provided
    # identity. The username comes from the localhost OIDC proxy and this
    # endpoint is protected by the broker secret.
    now = datetime.utcnow()
    if entitlement.status.value != "active" or entitlement.expires_at <= now or entitlement.code_version != policy.code_version:
        raise HTTPException(403, "Access denied")
    showroom_url = workspace_url = console_url = None
    lab_session = provisioning_service._public_access_session(policy.order_id, entitlement.seat_ref)
    if policy.order_type == "workshop":
        workshop = provisioning_service.get_workshop(policy.order_id)
        seat = next((item for item in (workshop.seats if workshop else []) if item.seat_id == entitlement.seat_ref), None)
        if seat:
            showroom_url, workspace_url = seat.showroom_url, seat.lab_url
    elif lab_session:
        showroom_url, workspace_url = lab_session.lab_url, lab_session.dashboard_url or lab_session.lab_url
    if lab_session and lab_session.cluster_ref and provisioning_service.cluster_registry:
        cluster = provisioning_service.cluster_registry.get(lab_session.cluster_ref)
        console_url = cluster.public_console_url or cluster.console_url
    public_access_service._audit("authorize", policy.order_id, "granted", identity.participant_id)
    return {"order_id": policy.order_id, "seat_ref": entitlement.seat_ref, "expires_at": entitlement.expires_at, "showroom_url": showroom_url, "workspace_url": workspace_url, "console_url": console_url}
