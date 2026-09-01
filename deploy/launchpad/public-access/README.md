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
3. Apply `oberon-ingresscontroller.yaml` with the real values and wait for
   Available.
4. Configure Keycloak and OpenShift OIDC.
5. Render and review `overlays/oberon-public`; then deploy it.
6. Run DNS, TLS, isolation, browser, authorization and cleanup certification.

Do not set `public_access_enabled: true` for Oberon until all steps pass.

The Keycloak authenticator image is built from `keycloak-authenticator/`.
`keycloak.yaml`, `keycloak-flow-config.json`, and `openshift-oauth-idp.yaml` are
merge templates, not directly deployable replacements. Back up the live
Keycloak/OAuth resources and merge only the described provider/client/flow.
Run `scripts/certify_public_access.py --host <test-order-host>` from an external
network and retain its immutable output in the certification evidence bundle.
