# Catalog journey and solution-family map

The catalog uses two independent axes:

- `solution_family` groups experiences by customer usage.
- `learning_level` describes progression from 001 exploration through 601
  governed authority.

The participant catalog groups cards by solution family and orders each group
by learning level. A learner can filter either dimension without forcing every
experience into one hierarchy.

The repository currently carries 25 non-deprecated catalog identities, 22
participant learning experiences, and one internal platform-validation
experience. `cpu-inference-serving` and `rag-on-xeon` are
API compatibility aliases for `intel-llm-cpu-serving`; participant discovery
hides those aliases so the 101 journey appears once. Administrative and direct
API views retain them temporarily for legacy consumers.

## Named learning tracks

The frontend must present named tracks separately from catalog lifecycle. A
track explains the path; it does not make a planned or draft lab orderable.
Only an active release with current certification receives an order action.

| Level | Agentic AI | Sovereign AI | Virtualization + AI |
| --- | --- | --- | --- |
| 101 | Understand Agentic Workflows — planned | Understand Sovereign AI — active, public one-seat certified | Understand VM and AI Coexistence — source-ready with per-seat VM identity; live proof pending |
| 201 | Build an AI Agent on Intel Xeon 6 | Build the Governed Inference Boundary — active, internal one-seat certified | Author and Qualify the Contract — active, internal one-seat certified |
| 301 | Build Multi-Agent Systems | Confidential Inference and Intel TDX Foundations — draft | Modernize VMs with Governed AI — active, public one-seat certified |
| 401 | Operate Evidence-Backed Agents — draft | Confidential AI with Intel TDX — source-qualified draft | Operate Hybrid VM and AI Workloads — source-qualified draft |
| 501 | Scale and Certify Agentic Systems — draft | Prove and Certify Sovereign AI — source-qualified draft | Scale Governed AI Modernization — source-qualified draft |
| 601 | Earn the Right to Act — source-qualified draft | Not offered | Not offered |

Sales enablement is a separate persona axis over these technical tracks. Sales
tracks may select different talk tracks, outcomes, and evidence while reusing a
certified runtime, but they must not silently create duplicate catalog releases
or imply technical certification. Their exact titles remain pending product
owner definition.

## Solution families

- Platform foundations: `ai-sandbox`, `openshift-operators-workshop`.
- Inference and RAG: the canonical `intel-llm-cpu-serving` experience. The
  `cpu-inference-serving` and `rag-on-xeon` identities are hidden compatibility
  aliases, not separate learner journeys.
- Agentic AI: `intel-xeon6-agent-201`, `intel-llm-tool-calling`, and
  `multi-agent-quickstart`.
- Operations and reliability: `agent-reliability`,
  `operate-agentic-blueprint`, `scale-agentic-blueprint`, and the deprecated
  `agentops-observability` reference.
- Industry solutions: `network-operations-agent` and
  `hybrid-fraud-detection`.
- Platform validation: `smoke-test`.

Catalog lifecycle and journey role are independent:

- `status` controls whether an item is active, draft, or deprecated.
- `journey_role` describes whether it is core, specialty, or reference.
- Draft and deprecated entries never become recommended merely because they
  appear on this map.

## Core journey

1. `ai-sandbox` — 001 Explore; the current Flightpath runtime is active and the
   reviewed guided-start enhancement awaits publish-and-pin recertification.
2. `intel-llm-cpu-serving` — 101 Learn.
3. `intel-xeon6-agent-201` — 201 Build.
4. `multi-agent-quickstart` — 301 Engineer.
5. `operate-agentic-blueprint` — 401 Operate; currently a draft content and
   certification candidate using this same runtime.
6. `scale-agentic-blueprint` — 501 Scale; currently a non-orderable charter
   that extends and certifies this same blueprint.

## Specialty episodes

- Tooling: `intel-llm-tool-calling`.
- Platform: `openshift-operators-workshop`.
- Domain: `hybrid-fraud-detection` and `network-operations-agent`.
- Reliability: `agent-reliability`.

Each episode retains its current lifecycle status. Network Operations,
Reliability, and Hybrid Fraud Detection are active and retain their historical
five-seat Flightpath evidence. Tool Calling is active with a source-corrected
journey awaiting post-publish one-seat recertification. The Operator Workshop
remains draft until its rebuilt OpenShift Pipelines journey passes a fresh
one-seat certification.

## Reviewed-source to Flightpath approval queue

The portfolio review covers all 25 catalog identities. The following
participant experiences now have corrected or expanded source candidates that
still need immutable publication, exact catalog pins, or fresh one-seat proof
before those changes can be treated as live:

- Platform foundations: `ai-sandbox`, `openshift-operators-workshop`.
- Inference and agent construction: `intel-llm-cpu-serving`,
  `intel-llm-tool-calling`, `intel-xeon6-agent-201`, and
  `multi-agent-quickstart`.
- Agentic operations: `operate-agentic-blueprint`,
  `scale-agentic-blueprint`, and `agentic-ai-601`.
- Sovereign AI: `sovereign-ai-101`, `sovereign-ai-201`,
  `sovereign-ai-301`, `sovereign-ai-401`, and `sovereign-ai-501`.
- Virtualization + AI: `virtualization-ai-foundations-101`,
  `virtualization-ai-201`, `virtualization-ai-301`,
  `virtualization-ai-401`, and `virtualization-ai-501`.
- Applied branches: `agent-reliability`, `network-operations-agent`, and
  `hybrid-fraud-detection`.

For each item, approval means that the catalog entry uses an immutable image
and source revision, all runtime and route settings are Flightpath-native, and
the one-seat certification run is GREEN-live. The current release ceiling for
new certifications is one seat. It must prove the complete participant
journey, required model calls, reclaim, and zero remaining resources before the
item changes from `draft` to `active`. Five-seat and higher runs are later
capacity-graduation gates, not a prerequisite for manual one-seat orderability.

Current convergence rules:

- `intel-llm-tool-calling` — source-ready; awaiting Flightpath one-seat proof.
- `openshift-operators-workshop` — source-ready; awaiting Flightpath one-seat
  proof.
- `ai-sandbox` — the current runtime has prior Flightpath evidence; the new
  guided-start source candidate must be published, pinned, and recertified.
- Sovereign 301/401/501, Virtualization 401/501, Agentic 501/601, and any other
  explicitly rehearsal-only journey remain draft after source publication.
  One-seat certification proves the rehearsal contract; it does not create a
  live hardware, confidential-computing, model, scale, or authority claim.
- `virtualization-ai-foundations-101` now has source-tested per-seat VM
  credentials and a certifier that executes through the Showroom terminal into
  the VM. It remains draft until the corrected Launchpad backend and immutable
  source are deployed and that exact VM-origin path is GREEN-live.
- `cpu-inference-serving` and `rag-on-xeon` — retained only as hidden API
  aliases for `intel-llm-cpu-serving`; they do not require separate curriculum
  certification unless product ownership decides to make them distinct again.

`smoke-test` is deliberately excluded from participant ordering. It remains an
internal platform-validation fixture.

## Reference archive

- `guided-rag-on-xeon` is deprecated reference content.
- `agentops-observability` is deprecated reference content. It is not the
  planned 401 experience and is not part of the canonical blueprint runtime.
- `smoke-test` remains a draft internal platform-validation fixture rather than
  participant curriculum.
