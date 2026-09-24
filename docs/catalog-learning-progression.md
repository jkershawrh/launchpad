# Catalog learning progression

Launchpad titles describe increasing learning depth while stable catalog IDs
continue to identify lifecycle, certification, telemetry, and reclaim records.
The level is curriculum metadata, not a claim about workload complexity or a
replacement for live certification.

## Levels

- **001 — Explore:** orientation, demonstrations, sandboxes, and platform
  familiarization with no prerequisite.
- **101 — Learn:** one foundational capability with a guided outcome.
- **201 — Build:** assemble and validate a working AI solution.
- **301 — Engineer:** integrate systems, protocols, evidence, authorization,
  and failure controls.
- **401 — Operate:** observe, govern, scale, and recover production-style AI
  systems.

The machine-readable authority is
[`../contracts/catalog-learning-progression-v1.yaml`](../contracts/catalog-learning-progression-v1.yaml).
Every catalog item declares its level, stage, experience type, prerequisites,
and recommended next items. Catalog IDs and workload versions do not change
when presentation metadata changes.

## Agentic learning path

The intended progression is:

1. `intel-llm-cpu-serving` — learn shared CPU inference.
2. `intel-llm-tool-calling` or `intel-xeon6-agent-201` — build tools or a
   single agent.
3. `multi-agent-quickstart` — engineer a multi-agent system.
4. `network-operations-agent` — apply evidence-backed agents to network
   operations.
5. `agent-reliability` — planned 301 lab for reliability controls, degraded
   behavior, authorization, recovery, and qualification.
6. `agentops-observability` — operate and observe production-style agents at
   level 401.

The network-operations and agent-reliability labs remain separate. The former
teaches a domain solution; the latter teaches how to engineer trustworthy
failure behavior. A shared NOC scenario is permitted because their learning
objectives and proof contracts are different.

## Compatibility and promotion

- Never encode the level into `catalog_item_id` or session identity.
- Existing sessions retain the catalog title captured by their release or use
  the current display title without changing lifecycle behavior.
- A title or learning-path change does not recertify a workload.
- Prerequisite and next-item references must resolve to known catalog IDs.
- Draft and deprecated items can appear in the progression contract without
  becoming participant-orderable.
- `smoke-test` is classified as 001 platform validation but remains an
  internal operational item rather than participant curriculum.
