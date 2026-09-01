# Public passwordless lab access

Public access is opt-in and release-gated. Existing orders remain internal
when `exposure_policy` is absent. A public order uses one URL and one instructor
code; the code is the sole secret and participant email is only an unverified
identity label.

## Personas

- **Platform operator:** configures `PUBLIC_LABS_DOMAIN`, wildcard DNS/TLS, the
  dedicated public ingress, WAF limits, Keycloak broker secret and OpenShift
  OIDC. Each execution cluster is certified independently.
- **Catalog owner:** verifies the Showroom, workspace, Console, model and
  cleanup journeys before permitting public placement.
- **Instructor:** copies the one-time code, distributes URL/code, monitors
  claimed seats, rotates the code when needed and reclaims the order.
- **Participant:** enters email plus the instructor code. The same normalized
  email can receive multiple active lab entitlements.
- **Release reviewer:** evaluates the evidence manifest, validation matrix and
  100-point rubric. A running pod is not acceptance evidence.

## Fail-closed activation

Both `PUBLIC_ACCESS_ENABLED=true` and a non-empty `PUBLIC_LABS_DOMAIN` are
required. The selected cluster must also set `public_access_enabled: true` and
provide public ingress, Console, OAuth and TLS configuration. Oberon is the
first target; Arena must be certified separately.

Only the entitlement-aware gateway, Keycloak, Console and OAuth routes may use
the public ingress. The normal backend, seat routes, Argo CD, databases, model
endpoints, admin APIs and internal service routes remain private.

## Proof package

- Contract: `contracts/public-access-v1.yaml`
- Behavior: `features/public_lab_access.feature`
- RED/GREEN record: `evidence/public-access/`
- Component suite: `backend/tests/test_public_access.py`

General availability requires every critical matrix row at `GREEN-live`, a
100/100 rubric, zero high/critical findings, three consecutive 25-seat browser
certifications and zero cleanup residue.
