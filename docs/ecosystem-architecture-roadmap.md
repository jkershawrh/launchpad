# Launchpad ecosystem architecture and scale roadmap

## Purpose and release boundary

Launchpad is the distributed control plane for ordering, placing, provisioning,
validating, using, observing, and reclaiming Intel and Red Hat lab experiences.
Git holds catalog, Showroom, deployment, certification, and operational
contracts. A workshop is one order with isolated participant seats; every seat
in an order stays on one execution cluster.

The current release is a **supervised internal pilot**, not a production or GA
service. Historical runs proved three staggered 25-seat workshops, 75
overlapping participant journeys, a 60-minute soak, and zero-residue reclaim.
The current retained topology again passed 75/75 functionality but is RED for
single-worker burst resilience after a node-wide probe storm restarted one
Arena ingress router. Manual visual acceptance, a fresh permanent-host public
claim, transport HA, and live per-seat LiteLLM attribution remain separate
gates.

## Certified current topology

```mermaid
flowchart LR
    U[Requester, instructor, participant] --> A[Arena Launchpad entry point]
    A --> API[Launchpad API and lifecycle workers]
    API --> DB[(PostgreSQL lifecycle state)]
    API --> ARGO[Arena Argo CD]
    API --> PA[Place whole workshop]
    PA --> EA[Arena execution]
    PA --> EB[Brutus execution]
    ARGO --> EA
    ARGO --> EB
    EA --> MA[25-seat Multi-Agent]
    EA --> LLM[25-seat Serve LLMs]
    EB --> AGENT[25-seat Building an AI Agent]
    API --> OBS[Admin operations and evidence]
```

| Capability | Current state | Boundary |
|---|---|---|
| Arena control plane | Active | API, database, requester/admin surfaces, lifecycle workers, Keycloak, and Argo CD |
| Arena execution | Certified for the two named 25-seat event workshops | The two orders are staggered; capacity is not a promise for arbitrary catalogs |
| Brutus execution | Certified for the 25-seat Building an AI Agent workshop | Internal access only; placement uses the persisted remote client |
| Oberon execution | Excluded | KubeVirt/HCO and namespace deletion must be remediated and recertified |
| Flightpath | Passive DR candidate | No active writer; promotion requires Arena fencing, restore, and a drill |
| Public participant access | Permanent-host pilot | `labs.smg-helix.ai` DNS/TLS/OIDC infrastructure is GREEN-live; participant claim/browser and transport-HA certification remain pending |
| Model attribution | Contract GREEN-local | Arena participant inference still uses direct OVMS/vLLM endpoints; live per-seat LiteLLM metrics are unavailable |

## Order-to-reclaim lifecycle

```mermaid
flowchart LR
    I[Git-pinned catalog intent] --> C[Capacity preview]
    C -->|whole order fits| R[Reserve aggregate capacity]
    C -->|does not fit| X[Reject before creating seats]
    R --> P[Persist workshop and cluster_ref]
    P --> S[Provision seats in bounded waves]
    S --> V[Functional validation]
    V --> H[Participant handoff]
    H --> O[Observe use and failures]
    O --> E[TTL or owner reclaim]
    E --> Z[Verify zero residue and release reservation]
```

The persisted `cluster_ref` is the lifecycle boundary. Create, validation,
retry, expiry, reclaim, and orphan reconciliation must always address that
cluster. Launchpad must never migrate an active seat, retry cleanup against a
different cluster, or split a workshop silently.

## Distributed execution contract

An execution cluster is eligible only when all required facts are known and
healthy:

- explicit API, ingress, Console, storage class, capabilities, and model routes;
- a dedicated least-privilege Launchpad credential stored outside Git;
- a separate Argo CD destination credential;
- durable, immutable images reachable from that cluster;
- sufficient measured CPU, memory, pod, storage, and node headroom;
- required Operators, model endpoints, route/WebSocket behavior, and cleanup;
- a successful 1 -> 5 -> 25 certification for each catalog/cluster pairing.

Missing credentials, health, capacity, or capabilities make the target
ineligible. A theoretical allocatable total is never a published seat limit.

## Scale roadmap

| Stage | Objective | Required proof | Status |
|---|---|---|---|
| Pilot baseline | Three staggered 25-seat orders; 75 environments active together | 75/75 journeys, isolation, soak, bulk reclaim, zero residue | GREEN-live automated; manual visual gate pending |
| Repeatable event | Re-run exact topology on demand | Three consecutive current-version runs, readiness percentiles, support rehearsal | Next operational gate |
| More catalogs | Add a quickstart repo without bespoke platform edits | Discovery, intake, source build, 1/5/25 proof contract | Scaffold introduced; adoption per catalog |
| More clusters | Register another CPU execution cluster | Least privilege, images, ingress, model routes, 1/5/25 gates | Playbook path defined |
| Larger workshops | 50 then 75 seats on one cluster | Measured headroom, node stability, functional load, reclaim | Do not advertise yet |
| Multi-event fleet | Concurrent orders across three or more targets | Queue fairness, capacity reservations, SLOs, failure-domain tests | Roadmap |
| Production service | Stable public ingress, HA/DR, security, support, ownership | Complete production rubric and drills | Post-pilot |

Provisioning performance should be improved through durable queues, bounded
seat waves, pre-seeded images, shared services, and measured cluster/catalog
percentiles. Shared services reduce duplicated pod cost only when namespace
isolation, availability, versioning, and ownership remain explicit. Per-seat
components should not be shared solely to make a capacity preview pass.

## Permanent production home and target architecture

The recommended production home is a dedicated OpenShift control-plane cluster,
referred to here as `launchpad-control-prod`. It is a logical target name, not a
decision to reuse Arena, Brutus, Flightpath, or Oberon. The production owner must
select the physical location, funding model, network boundary, support team, and
recovery site through an architecture review.

The permanent control-plane cluster should not host participant lab workloads or
large model-serving workloads. Keeping those failure domains separate allows the
platform to continue accepting lifecycle events, observing active orders, and
reclaiming resources when an execution or AI-serving cluster is impaired.

```mermaid
flowchart TB
    USERS[Participants, instructors, content teams, operators]
    EDGE[Managed DNS, TLS, WAF and identity-aware ingress]
    USERS --> EDGE

    subgraph CP[Dedicated production control plane]
        PORTAL[Requester, participant and admin portals]
        API[Launchpad API]
        QUEUE[Durable lifecycle queue and fenced workers]
        POLICY[Policy, governance and approval service]
        DB[(HA PostgreSQL)]
        GITOPS[Argo CD or approved GitOps controller]
        OBS[Metrics, logs, traces, evidence and audit]
        COST[Usage ledger, rate cards and chargeback]
        API --> QUEUE
        API --> POLICY
        API --> DB
        QUEUE --> DB
        QUEUE --> GITOPS
        API --> COST
        QUEUE --> OBS
    end

    EDGE --> PORTAL
    PORTAL --> API

    subgraph EXEC[Placement and execution fleet]
        E1[CPU and operator cluster]
        E2[Workshop cluster]
        EN[Additional certified clusters]
    end

    subgraph AI[Shared AI-serving plane]
        GATEWAY[Inference gateway and model catalog]
        ROUTER[Policy and semantic router]
        CPU[CPU model-serving pool]
        ACCEL[Accelerator model-serving pool]
        GATEWAY --> ROUTER
        ROUTER --> CPU
        ROUTER --> ACCEL
    end

    GITOPS --> E1
    GITOPS --> E2
    GITOPS --> EN
    QUEUE --> E1
    QUEUE --> E2
    QUEUE --> EN
    E1 --> GATEWAY
    E2 --> GATEWAY
    EN --> GATEWAY
    AI --> OBS

    DR[Warm control-plane recovery site]
    DB -. encrypted backup or replication .-> DR
    GITOPS -. immutable configuration .-> DR
```

### Production control-plane responsibilities

The production control plane owns the business and lifecycle state of the
service:

- one stable requester, participant, and administrator entry point;
- enterprise identity federation, tenant policy, entitlement, and
  namespace-scoped authorization;
- catalog, workshop, seat, reservation, `cluster_ref`, and expiration state;
- durable provisioning and reclaim jobs with leases, fencing, idempotency, and
  dead-letter handling;
- GitOps application generation and cluster-specific credential selection;
- global observability, audit history, immutable certification evidence, and
  usage accounting;
- policy-controlled remediation with an authenticated approval path;
- encrypted backup, restore, failover, and failback procedures.

Production deployment requires multiple API and lifecycle-worker replicas,
highly available PostgreSQL, durable object storage for evidence and backups,
an approved secrets manager, immutable images, and a warm recovery site in a
separate failure domain. The current Flightpath design can inform the recovery
pattern, but the production home and recovery site require an explicit platform
ownership decision.

### Placement and execution clusters

Execution clusters are replaceable capacity pools. Each cluster publishes a
versioned capability and health record that includes API and ingress reachability,
OpenShift version, installed Operators, storage classes, model connectivity,
network boundary, image reachability, allocatable and reserved resources,
failure history, and certified catalog/seat limits.

Placement uses two stages:

1. **Deterministic eligibility:** reject any cluster missing a required
   capability, credential, model, image, network path, storage class, policy,
   or complete-order capacity. These rules are never bypassed by AI.
2. **Auditable scoring:** rank eligible clusters by retained headroom,
   catalog-specific success rate, startup percentile, current reservations,
   failure-domain preference, network locality, energy or cost policy, and
   recent instability. Persist the inputs, score, explanation, policy version,
   and selected `cluster_ref` before creating resources.

Forecasting may later predict workshop readiness or saturation from historical
data. A model may recommend a target only among the deterministically eligible
set. The deterministic scorer remains the fallback when prediction is missing,
stale, low-confidence, or unavailable.

One workshop remains on one execution cluster in the initial production model.
Fleet-level scheduling can place separate workshops on different clusters. A
future split-workshop feature requires an explicit product decision because it
changes participant support, failure handling, networking, evidence, and
reclaim semantics.

### Shared AI-serving and semantic routing plane

The preferred AI architecture separates model serving from participant
namespaces. A shared inference gateway issues tenant/order/seat-scoped
credentials and routes requests to certified CPU or accelerator pools. The
model catalog records model version, endpoint, hardware class, data policy,
context limit, availability, latency, throughput, and rate-card metadata.

Semantic routing should use the least complex method that meets the product
need:

- explicit catalog policy for labs that require a specific model;
- deterministic task classification for embeddings, reranking, chat, tool use,
  and larger generation tasks;
- measured health, latency, capacity, data-boundary, and cost constraints;
- embedding or lightweight classifier routing only when prompts cannot be
  categorized reliably from catalog metadata;
- an optional LLM router only after deterministic and classifier approaches
  fail a measured quality requirement.

Every inference decision must record the requested capability, chosen model and
version, route reason, fallback, latency, token or request usage, tenant, order,
seat, and cost attribution without recording prompt content unless an approved
data policy permits it. Model endpoints remain private. Execution clusters
reach the gateway through approved private network paths, and unavailable model
capabilities remove a cluster/catalog pairing from placement eligibility.

### Intelligent reclamation and lifecycle closure

Reclaim is a first-class workflow rather than a best-effort delete operation.
Each order has an ownership ledger containing every namespace, Application,
Route, RoleBinding, credential, model key, storage claim, reservation, and
external integration created for it.

The production reclaim controller should:

1. deny participant access and revoke model credentials at TTL or owner action;
2. fence new mutations for the order and enqueue an idempotent reclaim job;
3. delete only ledger-owned resources through the persisted cluster client;
4. verify absence across Kubernetes, GitOps, identity, model gateway, storage,
   and Launchpad state;
5. release the capacity reservation only after closure or record a quarantined
   exception with an owner and retry time;
6. retain sanitized evidence and chargeback records according to policy.

Rules and ownership labels handle normal reclaim. AI is useful for classifying
unusual residue, correlating repeated failures, estimating the safest known
runbook, and proposing a bounded action. AI should not infer ownership or delete
unlabeled resources. Ambiguous resources, storage loss, RBAC changes,
cluster-scoped objects, and cross-cluster recovery require human approval.

## AI use within the product

AI should be added only where it improves a measured operating outcome. The
core order, policy, authorization, reservation, and ownership contracts remain
deterministic.

| Product decision | Default mechanism | Optional AI contribution | Required boundary |
|---|---|---|---|
| Eligibility | Versioned policy and live facts | None | AI cannot make an ineligible target eligible |
| Placement | Deterministic filter and score | Demand forecast, readiness estimate, anomaly-aware recommendation | Persist inputs and explanation; deterministic fallback |
| Provisioning | Declarative plans and durable jobs | Classify failures and recommend a known retry or runbook | Allow-listed actions, retry budget, post-validation |
| Model routing | Catalog requirement and policy router | Semantic task classifier when metadata is insufficient | Data policy, model allow-list, observable fallback |
| Reclaim | Ownership ledger and idempotent controller | Residue correlation and bounded remediation proposal | Never infer ownership; approval for ambiguous deletion |
| Support | Runbooks, evidence, and service ownership | Summarize incidents and retrieve relevant proof | No secret or unrestricted telemetry disclosure |
| Chargeback | Metered usage and versioned rate cards | Forecast demand and detect cost anomalies | Finance-approved rules remain authoritative |

The platform does not need a general-purpose AI decision layer for ordinary
CRUD, policy enforcement, identity, catalog validation, or accounting. Adding
one there would increase audit and failure complexity without improving the
service contract.

## Usage accounting, showback, and chargeback

The business solution needs a usage ledger before it needs billing. Every
accepted order should carry tenant, requester, cost center, catalog version,
workshop, seat count, selected cluster, and rate-card version. Runtime meters
then attribute:

- reserved and consumed CPU-core hours and memory GiB-hours;
- accelerator hours by type, model, and serving pool;
- storage GiB-months and retained evidence or dataset storage;
- model requests, input/output tokens where available, and gateway tier;
- public egress or other material network usage;
- shared control-plane and observability overhead using a documented allocation
  method;
- optional support or custom-content cost when the business model requires it.

The calculation should separate **estimated at order time**, **reserved during
the workshop**, and **actual after reclaim**. Versioned rate cards preserve the
price assumptions used for each order. The first release should provide
showback and budget alerts. Enforced quotas or internal chargeback follow only
after Finance, product ownership, and tenants approve the allocation rules and
two billing periods reconcile against infrastructure measurements.

Recommended business views are:

- tenant and cost-center spend by month;
- cost per workshop, participant seat, catalog, and completed learner journey;
- reserved versus consumed capacity and idle reservation cost;
- model and hardware cost by workload type;
- provisioning failure, retry, and stranded-resource cost;
- forecast demand, budget threshold, and cluster expansion signal.

Do not present the current `cost_estimate` field as an invoice. It remains a
showback estimate until the usage ledger, rate cards, reconciliation, dispute
process, and ownership model pass their contracts.

## Intel-led prospective sales motion

Launchpad should operate as an Intel-focused solution experience and technical
qualification platform powered by Red Hat OpenShift. It does not replace the
Red Hat Demo Platform. Approved Intel experiences may later graduate into RHDP,
but Intel owns the primary catalog, hardware fleet, model endpoints, telemetry,
capacity, business attribution, and prospective sales process.

The prospective motion connects a workshop to a production decision:

```mermaid
flowchart LR
    A[Target account and use case] --> W[Intel technical workshop]
    W --> Q[Workload qualification]
    Q --> P[Customer-specific proof]
    P --> S[Architecture, sizing and cost]
    S --> O[OEM, partner and Red Hat proposal]
    O --> D[Production deployment]
    D --> E[Expansion to more workloads]
```

### Catalog qualification ladder

| Experience | Prospective sales purpose | Expected next action |
|---|---|---|
| Serve LLMs on Intel Xeon | Establish whether CPU inference meets the workload's functional, latency, throughput, and cost needs | Size a customer-specific inference proof |
| Building an AI Agent | Identify an initial enterprise agent use case and required tools, data, and controls | Hold an architecture discovery session |
| Build Multi-Agent AI Systems | Qualify orchestration, protocol, model, tool, and governance requirements | Select one production-shaped workflow |
| AgentOps | Expose observability, evaluation, audit, support, and operating-model needs | Define the production operations proof |
| DeepField, StarGate, and GCL or GeoLux paths | Demonstrate fleet signals, validation, governed decisions, and bounded remediation | Review the control and integration architecture |
| Customer-specific experience | Validate the customer's approved model, data shape, workload, and target Intel architecture | Produce a decision package and partner proposal |

The first three experiences create technical interest and qualification. The
operations experiences establish what the customer needs to run the workload
reliably. A customer-specific proof should begin only after an account team and
customer agree on the decision it must support.

### Technical opportunity record

An order may carry an optional sales context containing opaque references to
the account, campaign, Intel seller, partner, Red Hat counterpart, and approved
CRM opportunity. The workshop result should produce a seller-safe technical
record containing:

- use case and intended business outcome;
- tested models, model sizes, concurrency, latency, and throughput requirements;
- data location, privacy, security, and regulatory constraints;
- measured CPU or accelerator fit and recommended Intel architecture;
- OpenShift, OpenShift AI, automation, storage, networking, and Operator needs;
- estimated infrastructure footprint and inference cost assumptions;
- production-readiness gaps, recommended next proof, owners, and decision date;
- evidence references, catalog version, cluster, and rate-card version.

Launchpad should not copy prompts, uploaded customer data, credentials, or
unrestricted operational telemetry into a CRM. Participant registration alone
does not create a sales lead. Any transfer of participant or account data must
follow an approved consent, retention, and access policy.

### Account-team operating model

| Party | Primary responsibility |
|---|---|
| Intel account owner | Select target accounts, own the opportunity, and connect the result to an approved sales record |
| Intel solution architect | Define success criteria, interpret workload evidence, and recommend the Intel architecture |
| Red Hat account or specialist team | Validate the OpenShift, OpenShift AI, Ansible, support, and services path when applicable |
| OEM, distributor, or integrator | Convert the validated architecture into a bill of materials, services plan, and commercial proposal |
| Customer technical owner | Supply the approved workload constraints, judge the proof, and own the production decision |
| Launchpad product and operations team | Deliver the governed environment, preserve evidence, and report only measured outcomes |

Within five business days of a qualifying workshop, the account team should
review the technical record and choose one outcome: close with a documented
reason, continue discovery, schedule a customer-specific proof, or attach the
result to an existing opportunity. The platform should record the outcome
without claiming commercial value before the opportunity owner accepts it.

### Funnel and attribution contract

Launchpad should report a progression rather than treating every participant
as pipeline:

1. registered participant;
2. completed participant journey;
3. technically qualified account;
4. sales-accepted follow-up;
5. customer-specific proof;
6. approved commercial opportunity;
7. proposed Intel/OEM architecture;
8. closed production deployment;
9. expanded workload or additional deployment.

An engagement counts as **sourced pipeline** only when the approved CRM rules
identify Launchpad as the originating motion. It counts as **influenced
pipeline** only after an opportunity owner attaches the evidence to an accepted
opportunity. Closed value must come from the authoritative sales system rather
than an estimate derived from registrations.

Primary product metrics are:

- production deployments influenced per qualified workshop;
- workshop-to-qualified-account conversion;
- qualified-account-to-customer-proof conversion;
- proof-to-proposal and proposal-to-deployment conversion;
- elapsed time from workshop to proof, proposal, and production decision;
- Intel architecture and OEM platform value influenced;
- attached Red Hat subscription or services opportunity where applicable;
- expansion revenue or additional workloads after the first deployment;
- cost per completed participant, qualified account, proof, and deployment.

The sales integration should begin with exported, reviewed evidence and an
opaque opportunity reference. A direct CRM write-back adapter follows only
after field ownership, consent, deduplication, error recovery, and attribution
contracts pass. This keeps the pilot useful to sellers without making CRM
integration a prerequisite for technical delivery.

## Migration path to the production home

The migration moves control-plane authority without moving active participant
namespaces between clusters. Existing sessions finish or reclaim on their
persisted execution target.

| Phase | Product outcome | Required exit evidence |
|---|---|---|
| 0. Supervised pilot | Preserve the current Arena control plane and certified Arena/Brutus pairings | Manual visual acceptance, current 3 x 25 evidence, support rehearsal |
| 1. Portable foundation | Remove cluster-local assumptions from images, secrets, storage, ingress, model routes, and configuration | Clean install and one-seat order on a temporary control-plane target |
| 2. Production home | Install the dedicated control plane, enterprise identity, HA database, durable queue, GitOps, evidence store, observability, and secrets management | Restore, restart, fencing, audit, and one-seat lifecycle tests |
| 3. Execution fleet | Register Arena, Brutus, and later clusters with dedicated provisioner and GitOps identities | Per catalog/cluster 1, 5, and 25 proof plus zero-residue reclaim |
| 4. AI-serving plane | Introduce the private model gateway, catalog, routing policy, scoped keys, and usage attribution | Required-model, fallback, isolation, load, and cost-meter tests |
| 5. Parallel verification | Mirror catalog and policy versions while the pilot remains the authority; send only controlled canary orders to the new home | Three consecutive mixed-cluster certification runs and reconciled usage data |
| 6. Controlled cutover | Drain new pilot orders, fence old control-plane writers, restore or replicate state, switch stable ingress, and enable new workers in order | Measured RPO/RTO, no duplicate writer, preserved `cluster_ref`, successful new order and reclaim |
| 7. Managed production | Add SLOs, on-call ownership, capacity forecasts, showback, approved chargeback, and graduated remediation | Production rubric, security review, DR drills, financial reconciliation, support sign-off |

The permanent URL should front the logical service rather than a cluster name.
DNS and identity stay stable when the control plane moves or fails over. Cluster
URLs remain implementation details exposed only where a participant explicitly
needs an OpenShift Console or lab endpoint.

## Production product roadmap

| Horizon | Product capability | Decision boundary |
|---|---|---|
| Internal pilot | Repeatable catalog, whole-workshop placement, guided participant experience, evidence, and zero-residue reclaim | Supervised operations and internal access |
| Durable service | Permanent control-plane home, HA lifecycle, stable identity/ingress, centralized observability, and tested DR | Production service ownership and SLO approval |
| Managed fleet | Policy-based cluster registration, reservations, predictive readiness, failure-domain placement, and capacity planning | Certified catalog/cluster pairs only |
| AI platform | Private multi-hardware serving, semantic routing where justified, per-seat attribution, and model governance | Deterministic eligibility and data policy remain authoritative |
| Business service | Intel-led opportunity qualification, tenant budgets, showback, rate cards, approved chargeback, catalog economics, and demand forecasts | Sales attribution and Finance-approved allocation rules |
| Governed autonomy | Evidence-driven recommendations followed by allow-listed automatic remediation and reclaim | One failure class earns autonomy at a time |

## Operations intelligence and auto-remediation

The proposed integrations are shared control-plane services, not a bundle
copied into every participant namespace.

```mermaid
flowchart LR
    DF[DeepField\nfleet and inference signals] --> SG[StarGate\nvalidation and failure class]
    LP[Launchpad lifecycle evidence] --> SG
    SG --> GD[GCL or GeoLux\ngoverned decision provider]
    GD --> POL[Launchpad remediation policy]
    POL -->|observe/recommend| OP[Operator]
    OP -->|approve when required| EX[Launchpad lifecycle executor]
    POL -->|allow-listed low risk| EX
    EX --> K8S[Persisted target cluster]
    K8S --> PV[Post-action functional validation]
    PV --> LP
```

| System | Intended role | Current maturity |
|---|---|---|
| Launchpad | Lifecycle authority, ownership, policy enforcement, execution, audit | Active pilot |
| StarGate | Preflight constraints, readiness evidence, failure classification, remediation callback contract | Adapter/contracts exist; production autonomy not certified |
| DeepField | Fleet, network, and inference signals for placement and incident context | Adapter exists; participant access and TLS hardening remain gated |
| GCL or GeoLux | Governed hypothesis/decision provider operating on bounded evidence | Selection and contract spike pending; neither is an execution authority |

GCL and GeoLux should first implement the same versioned decision-provider
contract: evidence references in, proposed action, confidence, constraints,
risk, explanation, and expiry out. Choose one after a contract spike measuring
fit, operability, security boundary, latency, and ownership. Deploying both
before that decision adds complexity without improving the pilot.

Remediation graduates one failure class at a time:

1. **Observe:** attach evidence; an operator follows the runbook.
2. **Recommend:** propose one bounded action and show affected resources.
3. **Approve:** an authenticated operator authorizes an idempotent execution.
4. **Automatic:** allow-list a low-risk action with retry budget, circuit breaker,
   post-validation, and escalation.

First candidates are delayed validation retry, owned Showroom resync, generated
Route reconciliation, bounded managed-workload restart, expired-session
reclaim, and stale-record repair. RBAC, Secrets, cluster-scoped Operators,
storage deletion, node repair, shared models, DNS/certificates, and cross-cluster
migration always require human authority.

## Source-of-truth map

| Concern | Repository contract |
|---|---|
| Cluster registry | `config/clusters.yaml` |
| Control-plane deployment | `deploy/launchpad/overlays/arena` and HA pilot overlay |
| Remote registration | `deploy/multicluster/` |
| Portable orchestration | `deploy/ecosystem/` |
| Catalog intake | `catalog-onboarding/<catalog-id>.yaml` |
| Catalog record | `catalog/<catalog-id>/catalog-item.yaml` |
| Learner journey | `content*/` Antora/AsciiDoc |
| Deterministic proof | `certification/catalog/` and `scripts/catalog_certification.py` |
| Immutable run evidence | `evidence/` and `evidence/runs/` |
| Support and recovery | `docs/support-runbook.md` and cluster-specific runbooks |

## Architecture decisions still open

- physical owner, region, funding source, and service name for the permanent
  production control-plane cluster;
- active/standby topology, database replication method, recovery objectives,
  and durable evidence/backup location;
- GCL versus GeoLux as the governed decision provider;
- durable public DNS, certificate, and ingress ownership;
- dedicated AI-serving cluster versus certified model pools distributed across
  execution clusters;
- live per-seat LiteLLM routing, semantic-routing policy, data retention, and
  attribution;
- Flightpath promotion/failback rehearsal and recovery objectives;
- third execution cluster and larger single-cluster workshop limits;
- showback allocation rules, rate-card ownership, budget enforcement, and the
  approval boundary for internal chargeback;
- approved CRM, consent and retention policy, account/opportunity ownership,
  and sourced-versus-influenced attribution rules for the Intel sales motion;
- service ownership and support rotations for a production deployment.
