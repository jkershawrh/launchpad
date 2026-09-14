# Arena permanent public pilot tunnel

Arena exposes the participant access gateway at
`https://labs.smg-helix.ai` through a Cloudflare named tunnel. The hostname and
DNS record are stable across pod restarts. Two fixed connector replicas now
provide pod/process failover; this remains a pilot transport until node-level
redundancy and the full public browser matrix are certified.

## Source of truth

- `kustomization.yaml` generates the router ConfigMap and applies the
  unprivileged tunnel ServiceAccount and Deployment.
- `deployment.yaml` runs two router-plus-`cloudflared` replicas using a pinned
  image, connection-aware `/ready` probes, rolling replacement, a disruption
  budget, and preferred worker anti-affinity.
- `partner-ai-launchpad/tunnel-token` supplies `TUNNEL_TOKEN` and is created
  out of Git.
- the Arena Launchpad overlay persists the public origin, path mode, placement
  eligibility, and strict OIDC gateway settings.
- `apply.sh` reconciles the Keycloak gateway client's callback because that
  client is stored in Keycloak rather than Kubernetes YAML.

The tunnel has no Kubernetes API token or RBAC. The script is pinned to
`/Users/jkershaw/.kube/config-arena` and refuses another cluster. Its base
reconcile never patches `OAuth/cluster`; the Arena custom Console route and
per-order Console flag remain a separately audited canary operation.

## Reconcile

```sh
./scripts/start-tunnel.sh
```

The command verifies the token Secret, applies the checked-in tunnel source,
persists `https://labs.smg-helix.ai`, updates only the Keycloak gateway client,
enables Arena public placement, and verifies edge health plus the OIDC issuer.

To move a still-active test order to the permanent origin without changing its
instructor code:

```sh
./scripts/start-tunnel.sh <public-order-id>
```

New orders should normally be created after reconciliation so their persisted
URL is correct from the beginning.

## Arena Console canary

Prepare the operator-managed custom Console route, then enable only an audited
order after its participant path is ready:

```sh
./scripts/certify-arena-public-console.sh prepare
./scripts/certify-arena-public-console.sh enable-order <public-order-id>
```

The script refuses a non-Arena API, requires the private-key TLS Secret to
already exist outside Git, retains the original route specification in an
in-cluster backup ConfigMap, waits for a healthy Console operator, verifies the
operator-managed callback, and changes the order through the admin API. Disable
an order without disturbing the cluster route with:

```sh
./scripts/certify-arena-public-console.sh disable-order <public-order-id>
```

Do not restore the cluster-wide Console route while any public order has its
Console flag enabled.

## Emergency stop

```sh
./scripts/stop-tunnel.sh
```

Stopping scales the gateway and tunnel to zero and writes explicit fail-closed
runtime overrides. Re-running `start-tunnel.sh` restores the checked-in state.

## Pilot boundary

The permanent hostname retires random tunnel URLs and repeated OAuth
propagation. On September 9, 2026, a controlled deletion of one of the two
connector pods produced zero failures across 120 external health, OIDC, and
protected-lab entry checks while Kubernetes replaced the pod. The deployment
is temporarily one active replica on `rhgnr1` while `gnr2` remains cordoned and
an old connector pod is still terminating there. This proves historical
connector/process resilience, not current worker or site resilience.
Long-lived WebSocket sessions may reconnect when their serving connector stops.

The September pilot gate covers participant login, My Lab Access, Showroom,
terminal, and declared lab tools. On September 14, one Arena seat also passed
the native OpenShift Console journey through the public origin: Keycloak SSO,
the assigned Pods page inside the Showroom tab, own-namespace edit, and
cross-namespace/node denial. The synthetic claim, RoleBinding, Keycloak user,
OpenShift User, and OpenShift Identity were removed afterward and the seat was
reopened. This result does not certify 25 concurrent Console users or Brutus.

The code exchange has an important invariant: rewrite the browser-facing
Keycloak Location back through `/oauth`, but preserve the nested native Arena
OAuth `redirect_uri` in the authorization request. Otherwise Keycloak binds
the code to the public callback while OpenShift redeems it with the native
callback and returns `Incorrect redirect_uri`.

The current custom-route certificate is pilot operational state. Replace it
with durable, monitored certificate management and prove rotation before
calling the Console path production-ready.
