# Handoff: Red Hat and Intel agentic blueprint and 401 lab

## Current state

This working tree contains the foundation and first content candidate for a
single episodic Launchpad journey built on the Red Hat and Intel evidence-backed
multi-agent blueprint.

The work is intentionally uncommitted on branch
`codex/flightpath-migration-20260922`. Review it before committing or pushing.

## Decisions already made

- Keep `multi-agent-quickstart` as the canonical 301 runtime.
- Keep existing domain and technology labs as specialty episodes rather than
  competing core journeys.
- Do not reuse the deprecated mortgage AgentOps experience as the new 401.
- Build 401 around the same orchestrator, agents, A2A, MCP, evidence, policy,
  Intel Xeon inference, and human-review boundaries used at 301.
- Treat lifecycle status independently from journey role. Draft and deprecated
  entries do not become orderable because they appear in the journey map.
- Reserve 501 for scale and certification; do not create or activate it before
  its certification gate exists.

## New foundation contracts

- `contracts/agentic-blueprint-v1.yaml`
- `contracts/agentic-journey-telemetry-v1.yaml`
- Extended `contracts/catalog-learning-progression-v1.yaml` with 501 and
  `core`, `specialty`, and `reference` roles.
- Added matching validation in
  `backend/app/services/catalog_onboarding.py`.
- Classified every existing catalog item with journey metadata.

Supporting documentation:

- `docs/red-hat-intel-agentic-blueprint.md`
- `docs/journey-telemetry-contract.md`
- `docs/catalog-journey-map.md`
- `docs/catalog-learning-progression.md`

## New 401 candidate

Catalog ID: `operate-agentic-blueprint`

Files:

- `catalog/operate-agentic-blueprint/catalog-item.yaml`
- `site-operate-agentic-blueprint.yml`
- `content-operate-agentic-blueprint/`
- `backend/tests/test_operate_agentic_blueprint_content.py`

The candidate reuses the digest-pinned `multi-agent-seat` chart and workload
image from `multi-agent-quickstart`. It is `status: draft`, limited to one seat,
and is not ready for participant ordering.

The linear content journey is:

1. Establish namespace, workload, model, and resource baseline.
2. Correlate a journey ID with request, response stages, latency, and logs.
3. Separate MCP evidence, deterministic policy, LLM explanation, and human
   authority.
4. Prove guardrail denial followed by a healthy clean request.
5. Apply an executor token policy, compare behavior, and restore baseline.
6. Assemble an operational proof package.

## Truth boundary

The content uses only capabilities currently present in the certified 301
runtime. It explicitly states that OpenTelemetry collection, Kagenti runtime,
GitOps drift reconciliation, pipeline evaluation, independent dependency
fault injection, and approved Intel CPU telemetry are not deployed in this
draft.

Do not activate the catalog item or rewrite those statements until live proof
exists.

## Activation blockers

The catalog item records these gates:

1. Implement `agentic-journey-telemetry-v1` correlation in the runtime.
2. Prove independent guardrail and inference outages, fail-closed behavior,
   and recovery.
3. Add certified OpenTelemetry collection and a learner-visible trace.
4. Validate namespace-scoped GitOps drift detection and pipeline evaluation.
5. Publish approved Intel Xeon latency, token, and CPU-allocation telemetry.
6. Pin immutable content provenance and complete one-, five-, and
   twenty-five-seat certification with zero-residue reclaim.

## Validation already completed

Using the repository Python 3.12 environment:

```text
Focused blueprint, catalog, onboarding, content tests: 52 passed
Full non-local backend suite: 2293 passed, 27 skipped, 13 deselected
All catalog, onboarding, and contract YAML parsed successfully
git diff --check: clean
```

The 13 deselected local-runtime tests require the local Podman services and are
not failures in this change.

## Recommended next work

1. Review the 401 learning flow and commands for the intended participant
   persona.
2. Build the Showroom package and visually inspect every page.
3. Implement native journey correlation in the canonical multi-agent workload
   rather than synthesizing it in the guide.
4. Add an independently addressable guardrail boundary so failure injection
   can be tested without terminating the compact workload pod.
5. Add approved OpenTelemetry and Intel endpoint telemetry incrementally, with
   contract tests first.
6. Replace `main` content references with immutable revisions.
7. Run one-seat certification before changing `status` or seat capacity.

