# Catalog journey and solution-family map

The catalog uses two independent axes:

- `solution_family` groups experiences by customer usage.
- `learning_level` describes progression from 001 exploration through 601
  governed authority.

The participant catalog groups cards by solution family and orders each group
by learning level. A learner can filter either dimension without forcing every
experience into one hierarchy.

## Named learning tracks

The frontend must present named tracks separately from catalog lifecycle. A
track explains the path; it does not make a planned or draft lab orderable.
Only an active release with current certification receives an order action.

| Level | Agentic AI | Sovereign AI | Virtualization + AI |
| --- | --- | --- | --- |
| 101 | Understand Agentic Workflows — planned | Understand Governed Inference — active, public one-seat certified | Understand VM and AI Coexistence — active, internal one-seat certified |
| 201 | Build an AI Agent on Intel Xeon 6 | Build the Governed Inference Boundary — active, internal one-seat certified | Author and Qualify the Contract — active, internal one-seat certified |
| 301 | Build Multi-Agent Systems | Confidential Inference and Intel TDX Foundations — draft | Modernize VMs with Governed AI — active, public one-seat certified |
| 401 | Operate Evidence-Backed Agents — draft | Confidential AI with Intel TDX — planned | Operate Hybrid VM and AI Workloads — planned |
| 501 | Scale and Certify Agentic Systems — draft | Prove and Certify Sovereign AI — planned | Scale Governed AI Modernization — planned |
| 601 | Earn the Right to Act — planned | Not offered | Not offered |

Sales enablement is a separate persona axis over these technical tracks. Sales
tracks may select different talk tracks, outcomes, and evidence while reusing a
certified runtime, but they must not silently create duplicate catalog releases
or imply technical certification. Their exact titles remain pending product
owner definition.

## Solution families

- Platform foundations: `ai-sandbox`, `openshift-operators-workshop`.
- Inference: `intel-llm-cpu-serving`, `cpu-inference-serving`.
- Generative AI and RAG: `rag-on-xeon`, `guided-rag-on-xeon`.
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

1. `ai-sandbox` — 001 Explore; currently draft pending a Flightpath-native
   runtime and certification contract.
2. `intel-llm-cpu-serving` — 101 Learn.
3. `intel-xeon6-agent-201` — 201 Build.
4. `multi-agent-quickstart` — 301 Engineer.
5. `operate-agentic-blueprint` — 401 Operate; currently a draft content and
   certification candidate using this same runtime.
6. `scale-agentic-blueprint` — 501 Scale; currently a non-orderable charter
   that extends and certifies this same blueprint.

## Specialty episodes

- Inference: `cpu-inference-serving`.
- Tooling: `intel-llm-tool-calling`.
- Data: `rag-on-xeon`.
- Platform: `openshift-operators-workshop`.
- Domain: `hybrid-fraud-detection` and `network-operations-agent`.
- Reliability: `agent-reliability`.

Each episode retains its current lifecycle status. Network Operations,
Reliability, and Hybrid Fraud Detection are active and retain their historical
five-seat Flightpath evidence. CPU Inference Serving, Tool Calling, RAG on
Xeon, the Operator Workshop, and the other legacy experiences remain draft
migration candidates. Their exact Flightpath runtime and one-seat proof
contracts are defined, but they are not permanently retired or orderable until
the corresponding GREEN-live runs pass.

## Legacy-to-Flightpath approval queue

The following learner experiences are preserved as migration candidates and
are intended to become orderable again:

1. `ai-sandbox`
2. `intel-llm-tool-calling`
3. `openshift-operators-workshop`
4. `rag-on-xeon`
5. `cpu-inference-serving`

For each item, approval means that the catalog entry uses an immutable image
and source revision, all runtime and route settings are Flightpath-native, and
the one-seat certification run is GREEN-live. The current release ceiling for
new certifications is one seat. It must prove the complete participant
journey, required model calls, reclaim, and zero remaining resources before the
item changes from `draft` to `active`. Five-seat and higher runs are later
capacity-graduation gates, not a prerequisite for manual one-seat orderability.

Current migration readiness:

- `intel-llm-tool-calling` — source-ready; awaiting Flightpath one-seat proof.
- `openshift-operators-workshop` — source-ready; awaiting Flightpath one-seat
  proof.
- `cpu-inference-serving` and `rag-on-xeon` — explicit compatibility entries
  on the proven Serve LLMs runtime; each still requires its own lifecycle and
  cleanup evidence.
- `ai-sandbox` — runtime and proof contracts are ready and its immutable GHCR
  image is published; anonymous image access plus Flightpath live proof remain.

`smoke-test` is deliberately excluded from participant ordering. It remains an
internal platform-validation fixture.

## Reference archive

- `guided-rag-on-xeon` is deprecated reference content.
- `agentops-observability` is deprecated reference content. It is not the
  planned 401 experience and is not part of the canonical blueprint runtime.
- `smoke-test` remains a draft internal platform-validation fixture rather than
  participant curriculum.
