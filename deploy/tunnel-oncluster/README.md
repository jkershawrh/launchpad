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
`/Users/jkershaw/.kube/config-arena` and refuses another cluster. It never
patches the Console operator, `OAuthClient/console`, or `OAuth/cluster`.

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
protected-lab entry checks while Kubernetes replaced the pod. Both replicas
currently run on `gnr2` because `rhgnr1` remains cordoned, so this proves
connector/process resilience, not worker or site resilience. Long-lived
WebSocket sessions may reconnect when their serving connector stops.

The September pilot gate covers participant login, My Lab Access, Showroom,
terminal, and declared lab tools. Native OpenShift Console access remains on
the internal/VPN path until separately approved and certified.
