# Agentic catalog journey map

Catalog lifecycle and journey role are independent:

- `status` controls whether an item is active, draft, or deprecated.
- `journey_role` describes whether it is core, specialty, or reference.
- Draft and deprecated entries never become recommended merely because they
  appear on this map.

## Core journey

1. `ai-sandbox` — 001 Explore.
2. `intel-llm-cpu-serving` — 101 Learn.
3. `intel-xeon6-agent-201` — 201 Build.
4. `multi-agent-quickstart` — 301 Engineer.
5. `operate-agentic-blueprint` — 401 Operate; currently a draft content and
   certification candidate using this same runtime.
6. A future 501 experience will scale and certify this same blueprint.

## Specialty episodes

- Inference: `cpu-inference-serving`.
- Tooling: `intel-llm-tool-calling`.
- Data: `rag-on-xeon`.
- Platform: `openshift-operators-workshop`.
- Domain: `hybrid-fraud-detection` and `network-operations-agent`.
- Reliability: `agent-reliability`.

Each episode retains its current lifecycle status. Network Operations,
Reliability, and Hybrid Fraud Detection remain draft until their catalog
activation and certification blockers are cleared.

## Reference archive

- `guided-rag-on-xeon` is deprecated reference content.
- `agentops-observability` is deprecated reference content. It is not the
  planned 401 experience and is not part of the canonical blueprint runtime.
- `smoke-test` remains internal platform validation rather than learner
  curriculum.
