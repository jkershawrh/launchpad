# Oberon multi-seat workshop readiness

## Supported envelope

The internal Intel Launchpad on Oberon supports one ordered workshop with up to
20 participant seats. Each seat receives an isolated namespace, demo workspace,
Showroom instance, persistent terminal home, and participant URL. The organizer
view exposes per-seat readiness, access URLs, CSV export, retry, and reclaim.

Twenty seats is the supported limit, not the theoretical cluster maximum. The
backend enforces it with `MAX_ACTIVE_SESSIONS_PER_WORKSHOP=20` and still performs
a fail-closed live capacity check before provisioning.

## Certified path

The 20-seat `guided-rag-on-xeon` certification on 2026-08-25 completed with:

- 20 of 20 seats ready
- 20 of 20 Argo CD applications `Synced` and `Healthy`
- 20 of 20 Showroom URLs returning HTTP 200
- the root Launchpad Argo CD application `Synced` and `Healthy`
- retry preserving already-ready seats and reusing deterministic namespaces

The successful nine-seat recovery pass completed in approximately 6 minutes 37
seconds after the Showroom chart cache was warm.

## Required Oberon settings

- `SHOWROOM_ROUTE_TIMEOUT=300`
- `MAX_ACTIVE_SESSIONS_PER_WORKSHOP=20`
- `WORKSHOP_PROVISION_CONCURRENCY=5`
- `WORKSHOP_RECLAIM_CONCURRENCY=10`
- Argo CD controller `ARGOCD_K8S_CLIENT_QPS=200`
- Argo CD controller `ARGOCD_K8S_CLIENT_BURST=400`

The Argo CD values are set on the operator-managed `ArgoCD/argocd` resource in
the `argocd` namespace. They prevent client-side throttling caused by Oberon's
large API/CRD discovery surface.

## Release posture

The platform is ready for controlled internal Intel workshops of up to 20
participants. Workshop reclaim is asynchronous: the organizer receives an
immediate accepted response and can follow persisted per-seat cleanup progress
until the workshop reaches `completed` or `completed_with_errors`.

Before broad unscheduled self-service, add concurrent-workshop admission policy,
load-test two simultaneous workshops, and publish organizer support/SLO
guidance.
