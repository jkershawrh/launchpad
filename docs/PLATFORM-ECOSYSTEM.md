# Intel x Red Hat AI platform ecosystem

This is a product-integration overview, not the architecture authority. Use
[`ecosystem-architecture-roadmap.md`](ecosystem-architecture-roadmap.md) for
the target architecture and
[`documentation-authority.md`](documentation-authority.md) when documents
disagree.

## Product boundaries

### Launchpad

Launchpad is the lifecycle control plane. It owns catalog releases, requester
and participant access, whole-workshop placement, capacity reservations,
provision/validate/reclaim jobs, evidence, audit, and usage attribution.

### StarGate

StarGate is a candidate validation and operations service. It can evaluate
versioned rubrics, classify known failures, and propose bounded remediation.
Launchpad remains authoritative for orders and mutations.

### DeepField

DeepField is a candidate observability and inference-intelligence service. It
can provide normalized fleet and model signals, anomaly detection, forecasting,
and advisory input to placement. Deterministic eligibility remains in
Launchpad.

### GCL or GeoLux

GCL/GeoLux represents the governed agentic-inference path: policy-constrained
reasoning, evaluation, review gates, and replay. It is an independently owned
solution integration, not a required dependency in every participant seat.

## Production topology

```text
participants, instructors, requesters, operators
                       |
stable public/internal edge and enterprise identity
                       |
dedicated Launchpad control-plane cluster
  API, portals, HA data, lifecycle workers, placement, policy,
  GitOps coordination, audit, evidence, usage and remediation
        |                    |                    |
execution-cluster fleet   AI-serving plane    software supply plane
warm namespace capacity   private gateway     build/scan/SBOM/sign
dedicated clusters when   CPU/accelerators    HA registry + mirrors
the catalog requires it   routing/governance  immutable digests
```

Arena is the pilot control-plane location. Arena, Brutus, Flightpath, and
future clusters are evaluated as execution or recovery targets by explicit
catalog/cluster certification. None is implicitly the permanent production
home.

## Integration contract

All optional products integrate through authenticated, versioned APIs or
events. An advisory integration may fail without blocking a deterministic
fallback. A required eligibility or authorization fact fails closed.

```text
Launchpad lifecycle event -> external evidence/evaluation service
External capacity/model signal -> Launchpad normalized signal contract
External remediation proposal -> Launchpad policy and approval gate
Launchpad cleanup result -> evidence and operations consumers
```

Required properties:

- unique event ID and idempotent consumption;
- bounded schema version and timestamp;
- authenticated service identity and trusted TLS;
- tenant/order/seat identifiers protected from metrics cardinality and public
  disclosure;
- no secret, prompt, response, or participant email in ordinary events;
- audit link from every recommendation to the eventual human or automated
  decision; and
- circuit breakers and stale-signal handling.

## Placement authority

Launchpad first filters clusters using deterministic requirements: API and
credential health, Operators, hardware, storage, ingress, network, model and
image availability, policy, and whole-order capacity. StarGate, DeepField, or
AI-assisted analysis may rank or explain only the eligible set. They cannot
grant access, bypass capacity, change ownership, or redirect cleanup.

The default delivery unit is a namespace-isolated seat on a warm execution
cluster. A catalog may instead require a dedicated workshop cluster or, in an
exceptional full-cluster curriculum, a dedicated seat cluster. The choice is a
certified catalog property.

## Artifact supply

All platform, Showroom, terminal, and lab workload images follow one promotion
path:

```text
immutable source -> reproducible CI build -> scan -> SBOM -> sign/attest
-> approved HA registry -> optional synchronized mirrors -> digest deployment
```

Execution-cluster registries are caches or mirrors. They are never the only
copy and never serve as a cross-cluster source of truth. Registry health,
credential validity, digest presence, architecture compatibility, cold-pull
latency, and replication freshness are placement and event-readiness signals.

## Deployment and GitOps

Kustomize and Argo CD reconcile versioned platform and shared-service desired
state. Launchpad's database and durable workers remain authoritative for
orders, reservations, assignments, entitlements, TTL, retries, and reclaim.
Do not create a Git commit for every seat.

RHDP, AgnosticV, and AgnosticD assets are retained as integration provenance
and optional adapter inputs. They are not the runtime architecture for the
current Intel pilot. Their presence does not make RHDP a production dependency.

## Graduation sequence

1. Contract and local component proof.
2. One-seat functional and security journey.
3. Five-seat concurrency and isolation.
4. Published-limit functional load on one certified cluster.
5. Public/internal exposure certification as separate gates.
6. Fault, restart, model-pressure, registry, and zero-residue reclaim proof.
7. Three consecutive releases before a pairing becomes generally eligible.

See [`production-solution-pathways.md`](production-solution-pathways.md) for
the solution-specific sequence and
[`ecosystem-enablement-proof-matrix.md`](ecosystem-enablement-proof-matrix.md)
for the evidence model.
