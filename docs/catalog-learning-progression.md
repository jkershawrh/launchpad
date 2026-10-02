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
- **501 — Scale:** scale, upgrade, secure, recover, and certify a production
  architecture. A 501 title is reserved for a workload that has passed its
  declared certification gate.

The machine-readable authority is
[`../contracts/catalog-learning-progression-v1.yaml`](../contracts/catalog-learning-progression-v1.yaml).
Every catalog item declares its level, stage, experience type, prerequisites,
and recommended next items. Catalog IDs and workload versions do not change
when presentation metadata changes.

## Core agentic learning path

The intended progression is:

1. `ai-sandbox` — explore OpenShift and shared Intel CPU inference; currently
   draft pending a Flightpath-native runtime and certification contract.
2. `intel-llm-cpu-serving` — learn shared CPU inference.
3. `intel-xeon6-agent-201` — build a bounded agent and MCP tools.
4. `multi-agent-quickstart` — engineer the canonical multi-agent system.
5. `operate-agentic-blueprint` — operate and recover that same system; active
   for bounded one-seat internal and public-code use.
6. `scale-agentic-blueprint` — qualify the deployment envelope through a
   bounded one-seat internal rehearsal.
7. `agentic-ai-601` — evaluate whether the system has earned authority through
   a bounded one-seat internal rehearsal; production action remains disabled.

The canonical architecture is
[`../contracts/agentic-blueprint-v1.yaml`](../contracts/agentic-blueprint-v1.yaml).
Its common live-proof record is
[`../contracts/agentic-journey-telemetry-v1.yaml`](../contracts/agentic-journey-telemetry-v1.yaml).

## Specialty episodes

Specialties branch from the core journey and teach a bounded domain, platform,
data, inference, tooling, or reliability outcome. Network Operations and Agent
Reliability remain separate specialties: the former teaches a domain solution;
the latter teaches trustworthy failure behavior. The full map and current
lifecycle status are documented in
[`catalog-journey-map.md`](catalog-journey-map.md).

The deprecated `agentops-observability` item is reference material only. It is
not the planned 401 runtime and does not define the canonical architecture.

## Compatibility and promotion

- Never encode the level into `catalog_item_id` or session identity.
- Existing sessions retain the catalog title captured by their release or use
  the current display title without changing lifecycle behavior.
- A title or learning-path change does not recertify a workload.
- Prerequisite and next-item references must resolve to known catalog IDs.
- Draft and deprecated items can appear in the progression contract without
  becoming participant-orderable.
- Journey role never overrides lifecycle status or certification.
- `smoke-test` is classified as 001 platform validation but remains a draft
  internal operational fixture rather than participant curriculum.
