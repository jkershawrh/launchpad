# Launchpad architecture

This document is the concise current architecture contract. The long-range
decisions and migration sequence are maintained in
[`ecosystem-architecture-roadmap.md`](ecosystem-architecture-roadmap.md), and
documentation precedence is defined in
[`documentation-authority.md`](documentation-authority.md).

## Current pilot

The pilot uses one Launchpad control plane on Arena and direct OpenShift
adapters to provision complete workshops onto explicitly registered execution
clusters. Flightpath, Arena, and Brutus are qualified only for the catalog and
seat envelopes proven on each of them; Oberon is excluded until its cluster
issues and catalog pairings are recertified. The permanent participant entry
point is `https://labs.smg-helix.ai`.

Every workshop persists one `cluster_ref` before any resource is created. All
seats in that workshop remain on that execution cluster. Provisioning,
validation, public access, expiration, reclaim, reconciliation, and orphan
cleanup use the persisted target and never retry against another cluster.

The September pilot uses namespace-isolated seats on warm clusters. It is not
a cluster-per-seat architecture. Current event orders may exceed an older
25-seat catalog baseline only where that exact catalog/cluster/exposure pairing
has a retained certification result.

## Production planes

```text
Stable public edge
  DNS + trusted TLS + WAF + identity + entitlement gateway
                         |
Dedicated control-plane cluster
  portals + API + HA database + durable workers + placement + policy
  GitOps coordination + evidence + audit + usage ledger + remediation
             |                              |
Registered execution fleet                 Shared AI-serving plane
  warm namespace capacity                    model gateway and catalog
  optional dedicated workshop clusters       CPU/accelerator pools
  certified catalog/cluster pairings          deterministic/semantic routing
             |
Durable software supply plane
  reproducible build -> scan -> SBOM -> sign -> attest -> HA registry
  -> optional regional/cluster pull-through mirrors
```

The control plane owns intent and lifecycle state. Execution clusters provide
replaceable capacity. The AI plane serves governed models. The edge provides
one participant experience. The registry provides independently recoverable
artifacts.

## Placement and capacity

Placement has two stages:

1. Fail-closed eligibility verifies cluster/API health, credentials, required
   Operators and capabilities, OpenShift version, storage, ingress, model
   availability, image reachability, network policy, and whole-order capacity.
2. Auditable scoring ranks eligible targets using retained headroom,
   reservations, catalog-specific success and latency, current model pressure,
   failure-domain preference, cost, and recent instability.

Launchpad reserves aggregate capacity before creating seats and revalidates it
immediately before provisioning. A workshop is rejected rather than silently
split. Active sessions are never migrated between clusters.

### Deployment classes

| Class | Use | Default lifecycle |
|---|---|---|
| Shared-cluster namespace lab | Ordinary application, agent, RAG, and operator-consumer labs | Place on a warm eligible cluster and create one isolated namespace per seat |
| Dedicated workshop cluster | Cluster-scoped changes, destructive administration, special networking/hardware, or stronger event isolation | Allocate one cluster to the whole workshop, then create isolated seats there |
| Dedicated seat cluster | A learning objective genuinely requires full-cluster control per participant | Explicit exception with a lower certified limit and a separate cost/reclaim contract |

Cluster creation is a fleet-capacity workflow below Launchpad, not the normal
seat workflow. Capacity automation maintains a warm pool, provisions clusters
ahead of forecast demand or scheduled events, registers and certifies them,
then drains and retires excess capacity safely.

## Artifact and content supply

Catalog records reference immutable image and content digests. CI builds once,
scans, produces an SBOM, signs and attests, then publishes to an approved
highly available registry such as Quay. The identical digest is promoted from
candidate to production.

Execution clusters pull from the authoritative registry or a synchronized
mirror. Their internal registries may cache images but must never be the only
copy or a dependency for another cluster. Placement fails closed when the
required digest, trust chain, credentials, architecture, or mirror freshness
cannot be proven. Large events pre-pull the exact release digests and retain
cold-pull evidence.

## Core product modules

| Module | Responsibility |
|---|---|
| `backend` | API, policy, placement, lifecycle, adapters, evidence, and persistence |
| `frontend` | requester and instructor workflows |
| `admin` | fleet, workshop, seat, model, reservation, and remediation operations |
| `content-*` | versioned Antora/AsciiDoc participant journeys |
| `catalog` | release and resource contracts for orderable experiences |
| `certification` | deterministic 1/5/25-or-published-limit proof contracts |
| `deploy/launchpad` | control-plane and shared-service deployment definitions |
| `deploy/workloads` | namespace-scoped or workshop-scoped workload packages |

Mock and local adapters remain development tools. Direct OpenShift is the
current Intel pilot path. RHDP/AgnosticV/AgnosticD material is retained as
integration provenance and an optional adapter contract; it is not the current
Intel runtime architecture or the permanent production control plane.

## Lifecycle authority

Git and Argo CD own long-lived platform, cluster baseline, and released catalog
desired state. Launchpad owns orders, reservations, workshop/seat assignments,
entitlements, TTLs, lifecycle jobs, and audit mutations. Kubernetes and
Operators converge resources. Certification proves functional readiness and
zero-residue reclaim; neither `Synced` nor `Running` is sufficient.

Durable workers use leases, fencing, idempotency, bounded retries, and a
dead-letter/manual-recovery path. Reclaim revokes access and model credentials,
deletes only ledger-owned resources on the persisted target, verifies absence,
then releases the reservation.

## Security and observability boundaries

Control-plane APIs, databases, GitOps, model endpoints, registries, and cluster
credentials remain private. The public edge exposes only approved participant
and identity paths. Every execution and GitOps identity is cluster-specific
and least privilege.

The admin product is the workflow system-of-record. Prometheus/Grafana provide
time-series views for cluster capacity, workshop/seat lifecycle, model
pressure, image supply, and remediation. Prompts, responses, secrets, emails,
and high-cardinality seat identifiers are not metric labels.
