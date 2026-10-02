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
| 101 | Understand Agentic Workflows — signed immutable presentation/runtime and direct Flightpath qualification green; Launchpad one-seat order/reclaim proof pending | Understand Sovereign AI — immutable candidate draft; live proof pending | Understand VM and AI Coexistence — immutable candidate draft with per-seat VM identity; live proof pending |
| 201 | Build an AI Agent on Intel Xeon 6 — published candidate draft; immutable workload pin and live proof pending | Build the Governed Inference Boundary — immutable candidate draft; live proof pending | Author and Qualify the Contract — immutable candidate draft; live proof pending |
| 301 | Build Multi-Agent Systems — immutable candidate draft; live proof pending | Confidential Inference and Intel TDX Foundations — immutable candidate draft; live TDX proof pending | Modernize VMs with Governed AI — immutable candidate draft; live proof and platform placement receipt pending |
| 401 | Operate Evidence-Backed Agents — active for bounded one-seat internal and public-code use; production gates remain | Confidential AI with Intel TDX — immutable candidate draft; live Trustee/KBS proof pending | Operate Hybrid VM and AI Workloads — immutable candidate draft; live proof pending |
| 501 | Scale and Certify Agentic Systems — active for bounded one-seat internal rehearsal; live execution and scale claims remain gated | Prove and Certify Sovereign AI — immutable candidate draft; destination proof pending | Scale Governed AI Modernization — immutable candidate draft; live proof pending |
| 601 | Earn the Right to Act — active for bounded one-seat internal rehearsal; production authority and scale remain gated | Not offered | Not offered |

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

1. `ai-sandbox` — 001 Explore; the guided-start enhancement is a draft awaiting
   publication, immutable pins, and one-seat recertification.
2. `intel-llm-cpu-serving` — 101 Learn.
3. `intel-xeon6-agent-201` — 201 Build; the current v1.0.9 candidate is a
   draft because its workload still uses a mutable tag and its thirty-seat
   evidence belongs to v1.0.8.
4. `multi-agent-quickstart` — 301 Engineer; the exact Story-enabled candidate
   is a draft awaiting one-seat recertification.
5. `operate-agentic-blueprint` — 401 Operate; active for bounded one-seat
   internal and public-code use. Its live Flightpath proof authorizes this
   pilot scope only; scale and production gates remain open.
6. `scale-agentic-blueprint` — 501 Scale; active for bounded one-seat internal
   rehearsal. Its signed candidate and one-seat lifecycle proof do not yet
   authorize live telemetry, multi-seat scale, or production claims.

## Specialty episodes

- Tooling: `intel-llm-tool-calling`.
- Platform: `openshift-operators-workshop`.
- Domain: `hybrid-fraud-detection` and `network-operations-agent`.
- Reliability: `agent-reliability`.

Each episode retains its current lifecycle status. Network Operations and
Hybrid Fraud Detection now have immutable source candidates; Reliability has a
published source update whose runtime image still belongs to the prior source.
All three remain draft until the exact candidate completes fresh one-seat
Flightpath proof. Their historical five-seat evidence remains useful historical
evidence but does not transfer to changed source. Tool Calling is likewise a
draft source-corrected journey awaiting one-seat recertification. The Operator
Workshop remains draft until its rebuilt OpenShift Pipelines journey passes a
fresh one-seat certification.

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

- `intel-llm-tool-calling` — source-ready draft; awaiting Flightpath one-seat
  proof and independent Intel backend provenance or a softened CPU claim.
- `openshift-operators-workshop` — source-ready; awaiting Flightpath one-seat
  proof.
- `ai-sandbox` — the prior runtime has Flightpath evidence; publication of the
  guided-start candidate currently fails closed on fixable HIGH/CRITICAL
  findings embedded in upstream OpenShift CLI and code-server payloads. Those
  payloads must be securely replaced or remediated before publication, pinning,
  and recertification; the security gate must not be weakened.
- `network-operations-agent` and `hybrid-fraud-detection` — immutable source
  candidates are pinned as drafts and need fresh one-seat proof.
- `agent-reliability` — the source update is published, but a matching immutable
  runtime image and fresh one-seat proof are still required.
- `virtualization-ai-foundations-101`, `virtualization-ai-201`, and
  `virtualization-ai-301` — exact source and available immutable images are
  pinned as drafts. All require new KubeVirt, Console, VM-origin, inference,
  reclaim, and zero-residue proof. The 101 source is still on its candidate
  branch; 301 also lacks an immutable Showroom-content image and needs a
  platform-owned placement receipt.
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
