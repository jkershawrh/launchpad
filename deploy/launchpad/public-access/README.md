# Oberon public ingress activation

The checked-in values use `.invalid` and cannot expose traffic accidentally.
Before activation, create a private environment overlay that replaces the
domain in the IngressController, wildcard Route, Launchpad ConfigMap and Oberon
cluster registry entry. Store `ACCESS_BROKER_KEY` in
`partner-ai-launchpad/launchpad-public-access`; do not commit it.

Activation order:

1. Provision a public load balancer/WAF and wildcard DNS.
2. Install the browser-trusted wildcard certificate Secret in
   `openshift-ingress`.
3. Install `rhbk-operator.yaml` and wait for the Red Hat Build of Keycloak
   Operator to report `Succeeded` in its dedicated `keycloak` namespace.
4. Apply `oberon-ingresscontroller.yaml` with the real values and wait for
   Available.
5. Configure Keycloak and OpenShift OIDC. When the Keycloak route uses the
   OpenShift ingress CA, copy only that public CA certificate into an
   `openshift-config/launchpad-keycloak-ca` ConfigMap and reference it from the
   OpenID provider. Do not set an insecure TLS bypass.
6. Render and review `overlays/oberon-public`; then deploy it.
7. Run DNS, TLS, isolation, browser, authorization and cleanup certification.

Do not set `public_access_enabled: true` for Oberon until all steps pass.

Oberon currently uses a single HostNetwork router on its only node. Do not
apply the sample `LoadBalancerService` IngressController until an external
load balancer/WAF and a reachable isolated endpoint have been designed. A
second router cannot share the default router's node ports on this topology.
The existing OSAC development Keycloak is unrelated and must not be reused.

The Keycloak authenticator image is built from `keycloak-authenticator/`.
`keycloak.yaml`, `keycloak-flow-config.json`, and `openshift-oauth-idp.yaml` are
merge templates, not directly deployable replacements. Back up the live
Keycloak/OAuth resources and merge only the described provider/client/flow.
Run `scripts/certify_public_access.py --host <test-order-host>` from an external
network and retain its immutable output in the certification evidence bundle.

## Arena named-tunnel pilot

Arena now uses the permanent `https://labs.smg-helix.ai` named tunnel described
in `deploy/tunnel-oncluster/README.md`. The checked-in workflow keeps Console
and authentication operators managed, uses an unprivileged tunnel identity,
loads its token from an out-of-Git Secret, updates an existing order only
through the audited Launchpad API, and never rotates the instructor code
implicitly. DNS, trusted TLS, health, OIDC discovery, and the Keycloak gateway
callback are GREEN-live. A fresh claim/callback and participant browser journey
are still required before public workshop access is certified.

The Keycloak authenticator first reuses its existing SSO cookie. If an embedded
OpenShift Console cannot send that cookie, the form can recover the unique
active order from the instructor code through the private
`validate-by-code` contract. Namespace RBAC must succeed before either path
returns a usable identity.

## Participant tool isolation

The public gateway resolves a participant's active entitlement before every
HTTP or WebSocket request. Its upstream allowlist contains only catalog-declared
workload Routes and registered cluster services for that persisted seat. An
undeclared Route in the same namespace is not exposed automatically.

Showroom `ui-config.yml` is rewritten per request so entitled tool tabs use
`/proxy/tool/<tool-id>/...`. External documentation remains external. The proxy
rejects traversal and cross-origin escapes, removes upstream cookie headers,
and rewrites same-origin redirects back through the gateway. These contracts
must still pass a deployed browser journey for every workload before a catalog
item is promoted from draft.
