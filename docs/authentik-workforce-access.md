# Authentik workforce access contract

## Boundary

Authentik governs people who request labs or operate Launchpad. It does not
replace participant email-plus-code access, participant Keycloak, namespace
RoleBindings, or the OpenShift identity used inside a lab.

| Surface | Identity authority | Authorization boundary |
| --- | --- | --- |
| Requester portal | Authentik OIDC | requester group plus tenant assignment |
| Admin portal | Authentik OIDC | explicit Launchpad role groups |
| Participant lab | existing Keycloak code flow | entitlement and seat namespace |
| OpenShift in a lab | existing participant identity | namespace-scoped RBAC |
| Automation | existing API keys, later workload identity | scoped API policy |

## Identity and role contract

Authentik is invitation-only for this phase. Email is an attribute, while the
OIDC `sub` claim is the immutable actor identifier. The backend accepts only a
signed RS256 token with the configured issuer, audience, expiration, signing
key, and non-empty subject.

Required claims are `sub`, `preferred_username`, `email`, and `groups`.

- `launchpad-requesters`: may open the requester portal.
- `launchpad-tenant:<tenant-id>`: assigns exactly that Launchpad tenant.
- `launchpad-tenant-managers`: may manage orders for assigned tenants.
- `launchpad-operators`: may inspect and operate lifecycle state.
- `launchpad-catalog-publishers`: may approve catalog promotion.
- `launchpad-auditors`: read-only evidence and audit access.
- `launchpad-admins`: full Launchpad administration; MFA is mandatory.

Group-to-permission enforcement beyond current admin/tenant checks is a
separate authorization increment. No group should be granted merely because a
user can authenticate.

## Security rules

1. Canary OIDC hostnames never accept `X-Forwarded-User`, email, or group
   headers as proof of identity.
2. oauth2-proxy performs browser login and forwards the signed token; the API
   independently verifies it.
3. Existing OpenShift-authenticated hostnames retain their current behavior
   during the canary and cannot silently switch identity providers.
4. Requester and admin cookies are separate, secure, SameSite=Lax, and bounded
   to eight hours. Admin access also requires `launchpad-admins` at the proxy.
5. Client secrets and cookie keys are external secrets, never Git content.
6. Disabled users, removed groups, expired tokens, wrong audiences, wrong
   issuers, missing keys, and unavailable JWKS all fail closed.
7. Authentik has a tested database backup and restore path and an audited
   break-glass administrator. Privileged users use MFA.

## Red/green validation matrix

| Evidence ID | Behavior | Local | Deployed canary | Promotion requirement |
| --- | --- | --- | --- | --- |
| AUTH-001 | Valid signed token becomes one stable user | GREEN | pending | identity shown correctly |
| AUTH-002 | Spoofed forwarded admin headers are rejected | GREEN | pending | HTTP 401 |
| AUTH-003 | Wrong issuer, audience, key, or algorithm is rejected | GREEN | pending | HTTP 401 |
| AUTH-004 | Expired or future token is rejected | GREEN | pending | HTTP 401 |
| AUTH-005 | Tenant group permits only its tenant | GREEN-unit | pending | cross-tenant denial |
| AUTH-006 | Non-admin cannot enter admin portal or admin API | GREEN-unit | pending | HTTP 403/denial |
| AUTH-007 | Current requester/admin routes are unchanged | GREEN-contract | pending | zero regression |
| AUTH-008 | Participant code login and lab SSO are unchanged | not touched | pending | full journey passes |
| AUTH-009 | User disable and group removal revoke access | contract | pending | bounded revocation proven |
| AUTH-010 | Authentik database restores successfully | contract | pending | restore drill evidence |

## Canary sequence

1. Provision durable Authentik and PostgreSQL; establish backup, restore, and
   break-glass procedures.
2. Create the `launchpad-workforce` OIDC provider and required groups.
3. Invite one requester, one tenant manager, one operator, and one admin.
4. Install the out-of-band Kubernetes secret and render the canary overlay.
5. Record the currently running deployment digests and active lab state.
6. Apply during a controlled window, then test only the new canary routes.
7. Prove correct tenant access, cross-tenant denial, admin denial, MFA,
   disable/revoke behavior, logout, restart recovery, and audit events.
8. Re-run one internal order and one external participant journey through the
   unchanged routes.
9. Roll back by removing the canary routes/proxies and clearing the OIDC host
   list. Do not cut over stable routes until every critical row is green.

## Current blocker

The repository package is deployable only after the Authentik hostname,
trusted certificate, OIDC client, secret delivery, and persistence/restore
decisions exist. Until then, it intentionally remains an unapplied canary.
