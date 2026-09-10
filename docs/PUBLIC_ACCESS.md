# Public passwordless lab access

Public access is opt-in and release-gated. Existing orders remain internal
when `exposure_policy` is absent. A public order uses one URL and one instructor
code; the code is the sole secret and participant email is only an unverified
identity label.

## Personas

- **Platform operator:** configures `PUBLIC_LABS_DOMAIN`, the approved DNS/TLS
  ingress mode, WAF limits, Keycloak broker secret and OpenShift OIDC. Each
  execution cluster is certified independently.
- **Catalog owner:** verifies the Showroom, workspace, Console, model and
  cleanup journeys before permitting public placement.
- **Instructor:** copies the one-time code, distributes URL/code, monitors
  claimed seats, rotates the code when needed and reclaims the order.
- **Participant:** enters email plus the instructor code. The same normalized
  email can receive multiple active lab entitlements.
- **Release reviewer:** evaluates the evidence manifest, validation matrix and
  100-point rubric. A running pod is not acceptance evidence.

## Fail-closed activation

Activation requires `PUBLIC_ACCESS_ENABLED=true`, the permanent
`PUBLIC_LABS_SHARED_ORIGIN=https://labs.smg-helix.ai`, shared path mode, and a
matching non-empty `PUBLIC_LABS_DOMAIN`. Arena is the only public-eligible pilot
target; Oberon, Brutus, and Flightpath remain fail-closed.

Arena now uses one account-managed Cloudflare named tunnel and the stable
single-origin path contract `https://labs.smg-helix.ai/labs/<order-ref>`.
The checked-in tunnel Deployment runs two fixed replicas with Cloudflare-edge
readiness probes, rolling replacement, a `minAvailable: 1` disruption budget,
and preferred worker anti-affinity. Autoscaling is intentionally disabled so a
scale-down cannot arbitrarily terminate a participant's long-lived connection.
`scripts/start-tunnel.sh` reconciles the checked-in named-tunnel Kustomize
source, strict OIDC settings, Keycloak client callback, backend/lifecycle
origin, and Arena cluster target. The token is loaded from the out-of-Git
`partner-ai-launchpad/tunnel-token` Secret. `scripts/stop-tunnel.sh` is the
explicit fail-closed emergency stop. Neither script changes the current
Kubernetes context or patches the Console operator, `OAuthClient/console`, or
`OAuth/cluster`.

The connector/process failover gate is `GREEN-live`: deleting one connector
produced zero failures across 120 external checks while the replacement became
Ready. Both connectors currently share `gnr2`, however, so Arena worker-level
public availability remains `RED` until another worker is qualified and the
same test passes with replicas on separate nodes. This distinction also means
that a currently open terminal WebSocket may reconnect during connector loss;
new and ordinary HTTP requests remained available in the certified test.

The reconciliation also pins both the Keycloak CR hostname and the
`launchpad-public` realm `frontendUrl` to the permanent origin. Verification
queries Keycloak through its private Service before trusting the public
discovery response, because the tunnel rewrites response bodies and cannot by
itself change the cryptographically signed token issuer.

Only the entitlement-aware gateway, Keycloak, Console and OAuth routes may use
the public ingress. The normal backend, seat routes, Argo CD, databases, model
endpoints, admin APIs and internal service routes remain private.

## Production ingress when wildcard DNS is prohibited

Intel's external-ingress policy does not permit wildcard DNS and permits only
HTTPS inbound traffic. That policy rules out the current per-order hostname
shape (`https://<catalog>-<order>.<PUBLIC_LABS_DOMAIN>`), but it does not rule
out public Launchpad access.

Use one of these mutually exclusive production patterns:

1. **Named Cloudflare Tunnel (preferred when outbound tunnel traffic is
   approved):** Intel creates one exact `labs.fm2aihpcsed.com` CNAME for a
   permanent, account-managed tunnel. Arena needs no public IP or inbound NAT.
   The firewall must permit `cloudflared` egress on TCP or UDP 7844; HTTPS-only
   browser traffic is unchanged. The hostname (or a delegated DNS zone
   containing it) must be managed in the same Cloudflare account as the
   tunnel; otherwise use the static-IP pattern. Quick Tunnels remain test-only.
2. **Static IP with HTTPS-only NAT:** Intel creates one exact
   `labs.fm2aihpcsed.com` A record and forwards TCP 443 to an isolated Arena
   ingress/gateway. TCP 80 is optional and is not a prerequisite. Certificate
   issuance must use DNS-01 or an Intel-provided public certificate because an
   HTTP-01 challenge cannot depend on port 80.

Both patterns require a single-origin URL contract. The selected named-tunnel
implementation uses `https://labs.smg-helix.ai/labs/<catalog>-<order>`. The entitlement gateway
must route order paths to private seat services and preserve WebSocket traffic.
Keycloak/OIDC callback URLs must use the same stable origin. Native OpenShift
Console exposure either needs separately approved exact Console and OAuth
hostnames or must remain behind the same tested gateway; dynamic seat Routes
must never be published individually.

### Multi-cluster participant routing

Running seats on Arena, Oberon, and Brutus must not change the participant
contract: one order URL, one instructor code, one participant identity, and one
My Lab Access page. The gateway resolves the entitlement to the session's
immutable `cluster_ref` and proxies Showroom, workspace, and terminal traffic
to that cluster's private ingress. Raw per-seat Routes remain private.

Each execution cluster must pass its own private DNS, ingress, WebSocket,
storage, and origin-health checks. Each OpenShift cluster must trust the same
stable Keycloak issuer, map the same opaque participant username, and create
RoleBindings only in that participant's assigned namespaces. Console/OAuth
callbacks must use stable, explicitly approved hosts or a separately certified
same-origin proxy. Public Console-through-tunnel remains outside the September
pilot gate.

Use one account-managed named Cloudflare Tunnel with redundant connectors and
explicit path/hostname rules, or one stable front door whose private network
can reach every target ingress. Do not expose multiple unrelated login pages or
give participants cluster-specific codes. If any target's DNS, TLS, Keycloak,
Console/OAuth, or external probe fails, public placement on that target fails
closed while internal placement may remain eligible.

Before implementing this mode, version the public-access contract and add RED
tests for path isolation, callback generation, multi-order routing, WebSockets,
cross-order denial, rotation, expiration and cleanup. Do not set a production
cluster's `public_access_enabled` flag from DNS approval alone.

Cloudflare references: [Kubernetes deployment](https://developers.cloudflare.com/tunnel/deployment-guides/kubernetes/),
[tunnel availability and failover](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-availability/),
[Tunnel firewall requirements](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/),
and [Quick Tunnel limitations](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

## Proof package

- Contract: `contracts/public-access-v1.yaml`
- Behavior: `features/public_lab_access.feature`
- RED/GREEN record: `evidence/public-access/validation-matrix-v7.yaml`
- Component suites: `backend/tests/test_public_access.py` and
  `backend/tests/test_public_tunnel_contract.py`

General availability requires every critical matrix row at `GREEN-live`, a
100/100 rubric, zero high/critical findings, three consecutive 25-seat browser
certifications and zero cleanup residue.
