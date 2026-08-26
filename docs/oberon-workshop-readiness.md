# Oberon multi-seat workshop readiness

## Supported envelope

The internal Intel Launchpad on Oberon supports one ordered workshop with up to
25 participant seats. Each seat receives an isolated namespace, Showroom guide,
Showroom instance, persistent terminal home, and participant URL. The organizer
view exposes per-seat readiness, access URLs, CSV export, retry, and reclaim.

Twenty-five seats is the configured supported limit, not the theoretical cluster maximum. The
backend enforces it with `MAX_ACTIVE_SESSIONS_PER_WORKSHOP=25` and still performs
a fail-closed live capacity check before provisioning.

## Certified path

The most recent fleet certification on 2026-08-26 ran three concurrently active
25-seat workshops: one on Oberon and two on Arena. It completed with:

- 75 of 75 seats ready
- 75 of 75 Argo CD applications `Synced` and `Healthy`
- 75 of 75 namespaces on their persisted target clusters
- representative Showroom URLs from all three workshops returning HTTP 200
- complete bulk reclaim with zero remaining namespaces or Applications
- no backend restart while provisioning was bounded to one workshop graph at a time

Measured 25-seat readiness was approximately 14 minutes 9 seconds on Oberon and
2 minutes 35 seconds to 2 minutes 54 seconds on Arena. These are certification
measurements, not yet published service-level objectives.

## Required Oberon settings

- `SHOWROOM_ROUTE_TIMEOUT=300`
- `MAX_ACTIVE_SESSIONS_PER_WORKSHOP=25`
- `WORKSHOP_PROVISION_CONCURRENCY=5`
- `WORKSHOP_RECLAIM_CONCURRENCY=10`
- Argo CD controller `ARGOCD_K8S_CLIENT_QPS=200`
- Argo CD controller `ARGOCD_K8S_CLIENT_BURST=400`

The Argo CD values are set on the operator-managed `ArgoCD/argocd` resource in
the `argocd` namespace. They prevent client-side throttling caused by Oberon's
large API/CRD discovery surface.

## Release posture

The platform supports controlled internal Intel workshop orders of up to 25
participants. Workshop reclaim is asynchronous: the organizer receives an
immediate accepted response and can follow persisted per-seat cleanup progress
until the workshop reaches `completed` or `completed_with_errors`.

Before broad unscheduled self-service, complete the visual Showroom-scale gate
below and publish organizer support guidance. Provisioning speed optimization,
queued workshop execution, and readiness ETA belong to the next iteration and
are tracked in `docs/next-iteration-roadmap.md`.

## Current release gate: visual Showroom scale

Run one 25-seat `openshift-operators-workshop` and validate the participant
experience in real browsers, not only with API probes:

- visually inspect seats 1, 5, 10, 15, 20, and 25
- confirm personalized participant, namespace, workshop, seat, and cluster values
- navigate every Antora page using both side navigation and next-page actions
- open the Terminal and run the documented authorization checks
- complete the operator discovery exercise
- deploy the hello workload and require `Hello OpenShift!` through its Route
- open the correct cluster Console and confirm Topology in the seat namespace
- verify no broken layout, stale content, wrong-cluster wording, or cross-seat data
- reclaim all 25 seats and require zero namespace/Application residue

Arena browser validation requires a trusted certificate for
`*.apps.arena.fm2aihpcsed.com`. Until that certificate is installed, Arena may
be used for API/load certification but cannot pass this browser release gate.

New orders use `openshift-operators-workshop`; the earlier Guided RAG catalog
item is deprecated and is not the canonical operator workshop.
