from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import provisioning_service, public_access_service
from app.auth.oauth import User, require_admin

router = APIRouter(prefix="/public-access", tags=["public-access"])
logger = logging.getLogger("launchpad.public_access")


class ClaimRequest(BaseModel):
    order_id: str
    email: str
    code: str


class CodeClaimRequest(BaseModel):
    email: str
    code: str


class IdentityClaimRequest(BaseModel):
    host: str
    username: str
    code: str
    public_path: str = ""


class IdentityCodeClaimRequest(BaseModel):
    username: str
    code: str


class PublicUrlRequest(BaseModel):
    public_url: str


def _require_broker(key: str) -> None:
    expected = os.getenv("ACCESS_BROKER_KEY", "")
    if not expected or not __import__("secrets").compare_digest(expected, key):
        raise HTTPException(403, "Forbidden")


def _participant_tool_urls(lab_session, catalog_item, cluster) -> dict[str, str]:
    """Return only catalog-declared tool endpoints for one persisted seat.

    The public gateway treats this mapping as its upstream allowlist. Route
    discovery alone is never enough: an undeclared Route in the namespace must
    not become reachable through a participant's public URL.
    """
    if not lab_session or not catalog_item:
        return {}
    metadata = catalog_item.metadata or {}
    route_names = metadata.get("workload_routes", {})
    route_urls = (lab_session.resources or {}).get("routes", {})
    service_urls = getattr(cluster, "service_urls", {}) if cluster else {}
    tools: dict[str, str] = {}
    for tab in metadata.get("showroom_tabs", []):
        tool_id = str(tab.get("id", ""))
        source = str(tab.get("source", ""))
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", tool_id):
            continue
        url = ""
        if source.startswith("workload.route."):
            route_id = source.removeprefix("workload.route.")
            route_name = str(route_names.get(route_id, ""))
            url = str(route_urls.get(route_name, ""))
        elif source.startswith("cluster.") and source.endswith("_url"):
            service = source.removeprefix("cluster.").removesuffix("_url")
            url = str(service_urls.get(service, ""))
        parsed = urlsplit(url)
        if parsed.scheme == "https" and parsed.netloc and not parsed.username:
            tools[tool_id] = url.rstrip("/")

    # Catalogs onboarded before declarative Showroom tabs identify their
    # participant application with workspace_route_name. Preserve that
    # contract through the same entitlement-aware, same-origin proxy used by
    # newer tool tabs. Do not infer any other Route from the namespace.
    workspace_route = str(metadata.get("workspace_route_name", "")).strip()
    has_declared_workspace = any(
        str(tab.get("source", "")).startswith("workload.route.")
        for tab in metadata.get("showroom_tabs", [])
        if isinstance(tab, dict)
    )
    if workspace_route and not has_declared_workspace:
        workspace_url = str(route_urls.get(workspace_route, ""))
        if not workspace_url:
            namespace = str(getattr(lab_session, "namespace", "") or "").strip()
            ingress_domain = str(
                getattr(cluster, "ingress_domain", "") or ""
            ).strip()
            dns_label = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
            dns_name = re.compile(
                r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$"
            )
            if (
                dns_label.fullmatch(workspace_route)
                and dns_label.fullmatch(namespace)
                and dns_name.fullmatch(ingress_domain)
            ):
                # Content-only labs can create their participant application
                # after the session's initial Route snapshot.  Derive only
                # the catalog-declared Route on the persisted seat namespace;
                # never expose arbitrary namespace Route discovery here.
                workspace_url = (
                    f"https://{workspace_route}-{namespace}.{ingress_domain}"
                )
        parsed = urlsplit(workspace_url)
        if parsed.scheme == "https" and parsed.netloc and not parsed.username:
            tools["workspace"] = workspace_url.rstrip("/")
    return tools


def _session_tool_urls(lab_session) -> dict[str, str]:
    if not lab_session:
        return {}
    catalog_item = provisioning_service.catalog.get_item(lab_session.catalog_item_id)
    cluster = None
    if lab_session.cluster_ref and provisioning_service.cluster_registry:
        cluster = provisioning_service.cluster_registry.get(lab_session.cluster_ref)
    return _participant_tool_urls(lab_session, catalog_item, cluster)


def _bind_claim_or_fail_closed(order_id: str, result) -> None:
    """Finish a claim only after Arena grants the participant's RBAC.

    Claim allocation and Kubernetes RoleBinding creation currently cross two
    storage systems. Compensate a failed binding by revoking the entitlement so
    Keycloak cannot issue a usable identity without namespace authorization and
    the seat remains available for a later retry.
    """
    try:
        provisioning_service.bind_public_participant(
            order_id,
            result.entitlement.seat_ref,
            result.identity.keycloak_username,
        )
    except Exception as exc:
        try:
            public_access_service.remove_participant(order_id, result.identity.participant_id)
        except Exception:
            logger.exception(
                "Failed to compensate participant claim after RBAC failure: "
                "order=%s seat=%s participant=%s",
                order_id,
                result.entitlement.seat_ref,
                result.identity.participant_id,
            )
        raise HTTPException(503, "Claimed environment is not ready") from exc


def _owner_summary(order_id: str) -> dict:
    policy = public_access_service.get_policy(order_id)
    if not policy:
        raise HTTPException(404, "Public access policy not found")
    entitlements = [
        entitlement
        for entitlement in public_access_service._entitlements.values()
        if entitlement.order_id == order_id and entitlement.status.value == "active"
    ]
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
    return {
        key: summary[key]
        for key in ("order_id", "enabled", "expires_at", "seat_limit", "claim_count")
    }


@router.post("/claim")
def claim(body: ClaimRequest, request: Request, response: Response):
    try:
        result = public_access_service.claim(
            body.order_id,
            body.email,
            body.code,
            request.client.host if request.client else "unknown",
        )
    except ValueError as exc:
        raise HTTPException(403, str(exc))
    _bind_claim_or_fail_closed(body.order_id, result)
    response.set_cookie(
        "launchpad_access",
        result.session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
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
        return {
            "authorized": True,
            "participant_id": session.participant_id,
            "seat_ref": entitlement.seat_ref,
        }
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
                identity = next(
                    (
                        item
                        for item in public_access_service._identities.values()
                        if item.participant_id == entitlement.participant_id
                    ),
                    None,
                )
                if identity:
                    provisioning_service.unbind_public_participant(
                        order_id, entitlement.seat_ref, identity.keycloak_username
                    )
        return {
            "one_time_access_code": public_access_service.rotate_code(order_id),
            **_owner_summary(order_id),
        }
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.patch("/admin/orders/{order_id}/public-url")
def update_public_url(
    order_id: str,
    body: PublicUrlRequest,
    _user: User = Depends(require_admin),
):
    try:
        public_access_service.set_public_url(order_id, body.public_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return _owner_summary(order_id)


@router.delete("/admin/orders/{order_id}/participants/{participant_id}", status_code=204)
def remove_participant(order_id: str, participant_id: str, _user: User = Depends(require_admin)):
    try:
        entitlement = public_access_service._entitlements.get((order_id, participant_id))
        identity = next(
            (
                item
                for item in public_access_service._identities.values()
                if item.participant_id == participant_id
            ),
            None,
        )
        if entitlement and identity:
            provisioning_service.unbind_public_participant(
                order_id, entitlement.seat_ref, identity.keycloak_username
            )
        public_access_service.remove_participant(order_id, participant_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/private/validate")
def keycloak_validate(
    body: ClaimRequest, request: Request, x_access_broker_key: str = Header(default="")
):
    _require_broker(x_access_broker_key)
    try:
        result = public_access_service.claim(
            body.order_id,
            body.email,
            body.code,
            request.client.host if request.client else "keycloak",
        )
    except ValueError:
        raise HTTPException(403, "Access request cannot be completed")
    _bind_claim_or_fail_closed(body.order_id, result)
    return {
        "active": True,
        "order_id": body.order_id,
        "subject": result.identity.participant_id,
        "preferred_username": result.identity.keycloak_username,
        "seat_ref": result.entitlement.seat_ref,
        "expires_at": result.entitlement.expires_at,
    }


@router.post("/private/validate-by-code")
def keycloak_validate_by_code(
    body: CodeClaimRequest,
    request: Request,
    x_access_broker_key: str = Header(default=""),
):
    """Validate Console OIDC when its callback host cannot identify an order.

    OpenShift's OAuth callback belongs to the cluster rather than an individual
    lab. The high-entropy instructor code is therefore used to select the one
    active policy before the normal atomic claim and RBAC binding path runs.
    """
    _require_broker(x_access_broker_key)
    now = datetime.utcnow()
    matches = [
        policy
        for policy in public_access_service._policies.values()
        if policy.enabled
        and policy.expires_at > now
        and public_access_service._verify(policy, body.code)
    ]
    if len(matches) != 1:
        raise HTTPException(403, "Access request cannot be completed")
    policy = matches[0]
    try:
        result = public_access_service.claim(
            policy.order_id,
            body.email,
            body.code,
            request.client.host if request.client else "keycloak",
        )
    except ValueError:
        raise HTTPException(403, "Access request cannot be completed")
    _bind_claim_or_fail_closed(policy.order_id, result)
    return {
        "active": True,
        "order_id": policy.order_id,
        "subject": result.identity.participant_id,
        "preferred_username": result.identity.keycloak_username,
        "seat_ref": result.entitlement.seat_ref,
        "expires_at": result.entitlement.expires_at,
    }


@router.get("/private/resolve")
def resolve_gateway_target(
    host: str,
    public_path: str = "",
    launchpad_access: str | None = Cookie(default=None),
    x_access_broker_key: str = Header(default=""),
):
    _require_broker(x_access_broker_key)
    policy = public_access_service.get_policy_by_request(host, public_path)
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
        seat = next(
            (
                item
                for item in (workshop.seats if workshop else [])
                if item.seat_id == entitlement.seat_ref
            ),
            None,
        )
        if seat:
            showroom_url = seat.showroom_url
            workspace_url = seat.lab_url
            lab_session = provisioning_service.get_session(seat.session_id or "")
        else:
            lab_session = None
    else:
        lab_session = next(
            (
                item
                for item in provisioning_service.list_sessions()
                if item.request_id == policy.order_id
            ),
            None,
        )
        if lab_session:
            showroom_url = lab_session.lab_url
            workspace_url = lab_session.metadata.get("workspace_url") or lab_session.dashboard_url
    if lab_session and lab_session.cluster_ref and provisioning_service.cluster_registry:
        target = provisioning_service.cluster_registry.get(lab_session.cluster_ref)
        # Public participants must never be redirected to the cluster's
        # private Console route. The tab stays unavailable until this target
        # has a separately certified public Console/OAuth path.
        console_url = target.public_console_url
        if console_url and lab_session.namespace:
            console_url = f"{console_url.rstrip('/')}/k8s/ns/{lab_session.namespace}/core~v1~Pod"
        if workspace_url and (
            "example.com" in workspace_url or ".apps.cluster.local" in workspace_url
        ):
            workspace_url = None
    return {
        "order_id": policy.order_id,
        "seat_ref": entitlement.seat_ref,
        "expires_at": entitlement.expires_at,
        "showroom_url": showroom_url,
        "workspace_url": workspace_url,
        "console_url": console_url,
        "tool_urls": _session_tool_urls(lab_session),
    }


@router.get("/private/order-by-host")
def order_by_host(
    host: str,
    public_path: str = "",
    x_access_broker_key: str = Header(default=""),
):
    _require_broker(x_access_broker_key)
    policy = public_access_service.get_policy_by_request(host, public_path)
    if not policy or not policy.enabled:
        raise HTTPException(404, "Public order not found")
    return {"order_id": policy.order_id, "expires_at": policy.expires_at}


@router.get("/private/resolve-identity")
def resolve_oidc_identity(
    host: str,
    username: str,
    public_path: str = "",
    x_access_broker_key: str = Header(default=""),
):
    _require_broker(x_access_broker_key)
    policy = public_access_service.get_policy_by_request(host, public_path)
    identity = next(
        (
            item
            for item in public_access_service._identities.values()
            if item.keycloak_username == username
        ),
        None,
    )
    if not policy or not policy.enabled or not identity or identity.disabled_at:
        raise HTTPException(403, "Access denied")
    entitlement = public_access_service._entitlements.get(
        (policy.order_id, identity.participant_id)
    )
    if not entitlement:
        raise HTTPException(403, "Access denied")
    # Reuse the target resolver's mapping without trusting a browser-provided
    # identity. The username comes from the localhost OIDC proxy and this
    # endpoint is protected by the broker secret.
    now = datetime.utcnow()
    if (
        entitlement.status.value != "active"
        or entitlement.expires_at <= now
        or entitlement.code_version != policy.code_version
    ):
        raise HTTPException(403, "Access denied")
    showroom_url = workspace_url = console_url = None
    lab_session = provisioning_service._public_access_session(policy.order_id, entitlement.seat_ref)
    if policy.order_type == "workshop":
        workshop = provisioning_service.get_workshop(policy.order_id)
        seat = next(
            (
                item
                for item in (workshop.seats if workshop else [])
                if item.seat_id == entitlement.seat_ref
            ),
            None,
        )
        if seat:
            showroom_url, workspace_url = seat.showroom_url, seat.lab_url
    elif lab_session:
        showroom_url = lab_session.metadata.get("showroom_url") or lab_session.lab_url
        workspace_url = lab_session.metadata.get("workspace_url") or lab_session.dashboard_url
    if lab_session and lab_session.cluster_ref and provisioning_service.cluster_registry:
        cluster = provisioning_service.cluster_registry.get(lab_session.cluster_ref)
        # Fail closed rather than leaking an internal Console hostname into a
        # public participant session.
        console_url = cluster.public_console_url
        if console_url and lab_session.namespace:
            console_url = f"{console_url.rstrip('/')}/k8s/ns/{lab_session.namespace}/core~v1~Pod"
        if workspace_url and (
            "example.com" in workspace_url or ".apps.cluster.local" in workspace_url
        ):
            workspace_url = None
    public_access_service._audit("authorize", policy.order_id, "granted", identity.participant_id)
    return {
        "order_id": policy.order_id,
        "seat_ref": entitlement.seat_ref,
        "expires_at": entitlement.expires_at,
        "showroom_url": showroom_url,
        "workspace_url": workspace_url,
        "console_url": console_url,
        "tool_urls": _session_tool_urls(lab_session),
    }


@router.get("/private/identity-entitlements")
def identity_entitlements(username: str, x_access_broker_key: str = Header(default="")):
    """Return every currently usable lab for one trusted OIDC identity."""
    _require_broker(x_access_broker_key)
    identity = next(
        (
            item
            for item in public_access_service._identities.values()
            if item.keycloak_username == username
        ),
        None,
    )
    if not identity or identity.disabled_at:
        raise HTTPException(403, "Access denied")
    labs = []
    for entitlement in public_access_service.entitlements_for(identity.participant_id):
        policy = public_access_service.get_policy(entitlement.order_id)
        if not policy or not policy.enabled:
            continue
        try:
            target = resolve_oidc_identity(
                host=policy.public_url.split("//", 1)[-1].split("/", 1)[0],
                username=username,
                public_path=urlsplit(policy.public_url).path,
                x_access_broker_key=x_access_broker_key,
            )
        except HTTPException:
            continue
        labs.append(
            {**target, "public_url": policy.public_url, "catalog_slug": policy.catalog_slug}
        )
    return {"username": username, "labs": sorted(labs, key=lambda item: str(item["expires_at"]))}


@router.post("/private/claim-identity")
def claim_oidc_identity(body: IdentityClaimRequest, x_access_broker_key: str = Header(default="")):
    """Add the lab addressed by host to an existing signed-in participant."""
    _require_broker(x_access_broker_key)
    policy = public_access_service.get_policy_by_request(body.host, body.public_path)
    identity = next(
        (
            item
            for item in public_access_service._identities.values()
            if item.keycloak_username == body.username
        ),
        None,
    )
    if not policy or not policy.enabled or not identity or identity.disabled_at:
        raise HTTPException(403, "Access request cannot be completed")
    try:
        result = public_access_service.claim(
            policy.order_id, identity.normalized_email, body.code, "oidc-gateway"
        )
    except ValueError:
        raise HTTPException(403, "Access request cannot be completed")
    _bind_claim_or_fail_closed(policy.order_id, result)
    return {"order_id": policy.order_id, "seat_ref": result.entitlement.seat_ref}


@router.post("/private/claim-identity-by-code")
def claim_oidc_identity_by_code(
    body: IdentityCodeClaimRequest,
    x_access_broker_key: str = Header(default=""),
):
    """Add an active lab by its instructor code from the participant hub."""
    _require_broker(x_access_broker_key)
    identity = next(
        (
            item
            for item in public_access_service._identities.values()
            if item.keycloak_username == body.username
        ),
        None,
    )
    if not identity or identity.disabled_at:
        raise HTTPException(403, "Access request cannot be completed")
    now = datetime.utcnow()
    matches = [
        policy
        for policy in public_access_service._policies.values()
        if policy.enabled
        and policy.expires_at > now
        and public_access_service._verify(policy, body.code)
    ]
    if len(matches) != 1:
        raise HTTPException(403, "Access request cannot be completed")
    policy = matches[0]
    try:
        result = public_access_service.claim(
            policy.order_id, identity.normalized_email, body.code, "participant-hub"
        )
    except ValueError:
        raise HTTPException(403, "Access request cannot be completed")
    _bind_claim_or_fail_closed(policy.order_id, result)
    return {
        "order_id": policy.order_id,
        "seat_ref": result.entitlement.seat_ref,
        "public_url": policy.public_url,
    }
