# Launchpad + StarGate Architecture (Historical Design)

> This is a design reference for a broader StarGate integration. It is not the current Oberon production contract.

## System Overview

```
                                    ┌─────────────────────────────┐
                                    │       Partner / Customer     │
                                    └──────────────┬──────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          LAUNCHPAD (Demo Platform)                           │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │Partner Portal │  │   Admin      │  │  Demo        │  │  Inference   │    │
│  │  (React)     │  │ Dashboard    │  │ Frontend     │  │  Gateway     │    │
│  │              │  │  (React)     │  │  (React)     │  │  (FastAPI)   │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                 │                  │             │
│         └────────────┬────┘─────────────────┘                  │             │
│                      ▼                                         │             │
│  ┌──────────────────────────────────┐                         │             │
│  │        Backend API (FastAPI)      │                         │             │
│  │                                   │                         │             │
│  │  ┌───────────┐ ┌───────────────┐ │                         │             │
│  │  │ Lifecycle  │ │  Provisioning │ │                         │             │
│  │  │  State     │ │   Service     │ │                         │             │
│  │  │  Machine   │ │               │ │                         │             │
│  │  └───────────┘ └───────┬───────┘ │                         │             │
│  │                        │         │                         │             │
│  │  ┌─────────┬───────────┼─────────┤                         │             │
│  │  │ Adapters │           │         │                         │             │
│  │  │         ┌▼──────┐   │         │                         │             │
│  │  │         │ Mock   │   │         │                         │             │
│  │  │         ├────────┤   │         │                         │             │
│  │  │         │ Local  │   │         │                         │             │
│  │  │         ├────────┤   │         │                         │             │
│  │  │         │OpenShft│   │         │                         │             │
│  │  │         ├────────┤   │         │                         │             │
│  │  │         │ RHDP   │───┼─────────┼──── Sandbox API ──────►│             │
│  │  │         ├────────┤   │         │                         │             │
│  │  │         │ AAP    │───┼─────────┼──── AAP Controller ───►│             │
│  │  │         └────────┘   │         │                         │             │
│  │  └──────────────────────┘         │                         │             │
│  └───────────────┬───────────────────┘                         │             │
│                  │                                              │             │
│                  │  ┌─────────┐                                │             │
│                  └─►│PostgreSQL│                                │             │
│                     └─────────┘                                │             │
└──────────────────────┬─────────────────────────────────────────┼─────────────┘
                       │                                         │
          ┌────────────┤                                         │
          │            │                                         │
          ▼            ▼                                         ▼
┌─────────────┐  ┌──────────┐                          ┌──────────────────┐
│ Sandbox API │  │ AgnosticD│                          │     LiteMaaS      │
│  (RHDP)     │  │ (ArgoCD) │                          │    (LiteLLM)      │
│             │  │          │                          │                   │
│ 12 CNV      │  │ tenant/  │                          │ ┌───────────────┐ │
│ clusters    │  │bootstrap/│                          │ │ Granite 3.2   │ │
│             │  │ Helm     │                          │ │ Llama 3.1 70B │ │
│ Namespace   │  │ chart    │                          │ │ DeepSeek R1   │ │
│ provisioning│  │          │                          │ │ Phi-4         │ │
└─────────────┘  └──────────┘                          │ │ Qwen3 14B    │ │
                                                       │ └───────┬───────┘ │
                                                       └─────────┼─────────┘
                                                                 │
                                                       ┌─────────┼─────────┐
                                                       │   Intel Hardware   │
                                                       │                    │
                                                       │  Gaudi 3 (24 cards)│
                                                       │  Xeon 6 (CPU)      │
                                                       └────────────────────┘
```

## Intelligence Layer (within Launchpad)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         LAUNCHPAD INTELLIGENCE                               │
│                                                                              │
│   LabRequest ──► OrchestrationBrain.decide()                                │
│                      │                                                       │
│                      ├── WorkloadClassifier.classify()                       │
│                      │     └── WorkloadProfile (type, GPU, intensity)        │
│                      │                                                       │
│                      ├── PlacementService.recommend_cluster()                │
│                      │     ├── StarGate capacity scores (cached, 60s poll)   │
│                      │     └── FeedbackTracker.should_avoid() filter         │
│                      │                                                       │
│                      ├── DeepFieldAdapter.get_fleet_overview()               │
│                      │     └── Penalize clusters with critical signals       │
│                      │                                                       │
│                      └── OrchestrationDecision                               │
│                            ├── recommended_cluster + hardware + quota        │
│                            ├── confidence (scales with signal diversity)     │
│                            ├── rationale (human-readable)                    │
│                            └── stored in session.resources["decision"]       │
│                                                                              │
│   After validation ──► FeedbackTracker.record_outcome()                     │
│                            └── ProvisioningOutcome → PostgreSQL             │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Launchpad ↔ StarGate Integration

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   LAUNCHPAD                                STARGATE                          │
│   (Orchestration Brain)                    (Validation + Capacity)           │
│                                                                              │
│   ┌────────────────────┐                   ┌────────────────────┐            │
│   │                    │   1. PRE-FLIGHT   │                    │            │
│   │  User orders demo  │──────────────────►│  Evaluate cluster  │            │
│   │                    │  "Can I provision  │  health, capacity, │            │
│   │                    │◄──here?"───────────│  known issues      │            │
│   │                    │  allowed/blocked   │                    │            │
│   └────────┬───────────┘                   └────────────────────┘            │
│            │                                                                 │
│            ▼                                                                 │
│   ┌────────────────────┐                                                     │
│   │                    │                                                     │
│   │  Provision demo    │                                                     │
│   │  (namespace,       │                                                     │
│   │   gateway,         │                                                     │
│   │   frontend)        │                                                     │
│   │                    │                                                     │
│   └────────┬───────────┘                                                     │
│            │                                                                 │
│            ▼                                                                 │
│   ┌────────────────────┐                   ┌────────────────────┐            │
│   │                    │   2. EVIDENCE     │                    │            │
│   │  Lifecycle events  │──────────────────►│  Record evidence   │            │
│   │                    │  provisioned,      │  Monitor health    │            │
│   │  validate → ready  │  validated,        │  Classify failures │            │
│   │  ready → active    │  activated,        │  Evaluate rubrics  │            │
│   │                    │  reclaimed         │                    │            │
│   └────────┬───────────┘                   └────────────────────┘            │
│            │                                                                 │
│            ▼                                                                 │
│   ┌────────────────────┐                                                     │
│   │                    │                                                     │
│   │  Reclaim triggered │                                                     │
│   │  (TTL expired,     │                                                     │
│   │   admin, workshop  │                                                     │
│   │   ended)           │                                                     │
│   │                    │                                                     │
│   └────────┬───────────┘                                                     │
│            │                                                                 │
│            ▼                                                                 │
│   ┌────────────────────┐                                                     │
│   │                    │                                                     │
│   │  Try cleanup       │                                                     │
│   │  directly:         │                                                     │
│   │  - delete namespace│                                                     │
│   │  - release sandbox │                                                     │
│   │  - scrub creds     │                                                     │
│   │                    │                                                     │
│   └───┬────────────┬───┘                                                     │
│       │            │                                                         │
│    SUCCESS       FAILURE                                                     │
│       │            │                                                         │
│       ▼            ▼                                                         │
│  ┌─────────┐  ┌────────────────────┐       ┌────────────────────┐            │
│  │RECLAIMED│  │                    │  3.   │                    │            │
│  │  (done) │  │  CLEANUP_FAILED   │──────►│  Pick up failure   │            │
│  └─────────┘  │  post evidence    │ CATCH │  Classify (LLM)    │            │
│               │                    │       │  Select remediation│            │
│               └────────────────────┘       │  Evaluate risk:    │            │
│                                            │   low → auto       │            │
│                                            │   med → approval   │            │
│                                            │   high → blocked   │            │
│                                            │                    │            │
│                                            │  Execute:          │            │
│                                            │  - oc delete ns    │            │
│                                            │  - sandbox-api del │            │
│                                            │  - force cleanup   │            │
│                                            └────────┬───────────┘            │
│                                                      │                       │
│               ┌────────────────────┐       4. CALLBACK                       │
│               │                    │◄────────────────┘                       │
│               │  Finalize reclaim  │  "I fixed it"                           │
│               │  CLEANUP_FAILED    │  result: success                        │
│               │  → RECLAIMED       │                                         │
│               └────────────────────┘                                         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Workshop Flow

```
Admin creates workshop (40 users)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Launchpad: provision_workshop()                         │
│                                                          │
│  for each user (1..40):                                  │
│    ├── Pre-flight check ──► StarGate: cluster healthy?   │
│    ├── Submit request                                    │
│    ├── Check session limits (2/user, 5/tenant)           │
│    ├── Provision (Sandbox API placement)                 │
│    ├── Validate                                          │
│    ├── Post evidence ──► StarGate: "provisioned"         │
│    └── Label: purpose=events, workshop-id=xxx            │
│                                                          │
│  Result: 40 sessions, all labeled, all tracked           │
│                                                          │
│  StarGate: monitors all 40 namespaces continuously       │
│                                                          │
│  Workshop ends → reclaim_workshop()                      │
│    ├── Reclaim each session (try direct, StarGate catch) │
│    ├── Track failures: completed / completed_with_errors │
│    └── Post evidence ──► StarGate: "workshop_ended"      │
└─────────────────────────────────────────────────────────┘
```

## Self-Service Flow

```
Partner logs in
    │
    ▼
┌─ Launchpad Portal ─────────────────────────────────────┐
│  Browse catalog (25 items)                              │
│  Select demo (e.g., Inference Overdrive)                │
│  Click "Launch Demo"                                    │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─ Launchpad Backend ────────────────────────────────────┐
│  1. Pre-flight ──► StarGate: allowed                   │
│  2. Submit request (check limits)                      │
│  3. Intelligence: classify workload, select hardware   │
│  4. Intelligence: recommend cluster (capacity + history)│
│  5. Sandbox API: claim namespace (preferred cluster)   │
│  6. ArgoCD: deploy tenant/bootstrap Helm chart         │
│     ├── Demo frontend (filtered pages)                 │
│     ├── Inference gateway (LiteLLM virtual key)        │
│     ├── PostgreSQL                                     │
│     └── NetworkPolicy + labels                         │
│  7. Validate (pod ready, route accessible)             │
│  8. Record outcome ──► FeedbackTracker (PostgreSQL)    │
│  9. Post evidence ──► StarGate: "ready"                │
│  10. Return Showroom URL + DecisionInsight to user     │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─ User Experience ──────────────────────────────────────┐
│                                                         │
│  Showroom (split view):                                 │
│  ┌─────────────────────┬───────────────────────────┐   │
│  │  Lab Instructions   │  [Terminal] [Console]      │   │
│  │                     │  [Demo Portal]             │   │
│  │  Step 1: Open the   │  ┌───────────────────┐    │   │
│  │  Demo tab...        │  │                   │    │   │
│  │                     │  │  Inference        │    │   │
│  │  Step 2: Compare    │  │  Overdrive        │    │   │
│  │  model latency...   │  │                   │    │   │
│  │                     │  │  Gaudi: 120ms     │    │   │
│  │  Step 3: Check      │  │  Xeon:  340ms     │    │   │
│  │  routing policy...  │  │  CPU:   890ms     │    │   │
│  │                     │  │                   │    │   │
│  └─────────────────────┴───┴───────────────────┘    │   │
│                                                      │   │
│  TTL expires → auto-reclaim → credentials scrubbed   │   │
└──────────────────────────────────────────────────────┘   │
                                                           │
  StarGate: monitoring namespace health throughout ────────┘
```

## Provisioning Modes

```
                    ┌─────────────────┐
                    │  Catalog Item    │
                    │  metadata:      │
                    │  provisioner_   │
                    │  mode: ???      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │   "rhdp"   │  │"openshift" │  │   "mock"   │
     │            │  │            │  │            │
     │  Sandbox   │  │  Direct    │  │  In-memory │
     │  API pool  │  │  K8s API   │  │  (testing) │
     │            │  │            │  │            │
     │  Self-svc  │  │ Persistent │  │  Dev/CI    │
     │  Workshops │  │ demos on   │  │            │
     │            │  │ infra01    │  │            │
     └────────────┘  └────────────┘  └────────────┘
```
