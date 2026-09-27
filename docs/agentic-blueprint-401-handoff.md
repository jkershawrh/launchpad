# Handoff: Red Hat and Intel agentic blueprint and 401 lab

## Current state

This working tree contains the complete candidate package for a single episodic
Launchpad journey built on the Red Hat and Intel evidence-backed multi-agent
blueprint: a Triforce-style pre-lab presentation followed by the 401 hands-on
operations lab.

The source and content candidate were committed on branch
`codex/flightpath-migration-20260922`. The catalog pins the Showroom content to
commit `ddd7c2aab25d4c10f7738f15eece1ab101a95b15`.

The presentation source is pinned to commit
`9cec3cebe7972b92385c55174674532eeb895f97` in
`jkershawrh/multi-agent-quickstart`.

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

The chart now has an opt-in presentation runtime contract. When the 401
catalog item enables it, Argo CD creates a separately owned presentation
Deployment, Service, edge Route, and ingress policy in the seat namespace. The
301 catalog item does not enable it and therefore renders unchanged.
The catalog pins that chart contract to Launchpad commit
`4da2ea8a23d40bc74d0836c741f4abd22770aa12`.

Immutable runtime artifact:

```text
quay.io/rh-ee-jkershaw/launchpad-multi-agent-quickstart@sha256:84f6be95993f6481b4d99f9e0d68e98e12d0ea9c992d204164a3688503e1c661
```

Immutable presentation artifact:

```text
quay.io/rh-ee-jkershaw/launchpad-operate-agentic-blueprint-presentation@sha256:2aee08aaac09e296725954a9450ffc87240b9a9ef458a291916127871259c580
```

The presentation uses the Triforce underpinning: a concise business opening,
guided architecture questions, the same architecture animated through live
proof, Intel Xeon inference, MCP evidence, deterministic policy, human
authority, measured payoff, closure, and only then the Launchpad lab handoff.
The canonical image was built without a seat-specific API URL. Launchpad
therefore serves it on a dedicated route and replaces its NGINX runtime
configuration with a same-origin `/api` proxy to the seat-local orchestrator.
The proxy injects the per-seat service token server-side from the existing
runtime Secret; that token is not exposed to the browser or serialized into
the Argo CD Application. The Showroom itself remains the lab handoff rather
than baking a dynamic participant URL into the image.

The image manifest was resolved successfully from Quay. Its current artifact
evidence is not sufficient for activation: the OCI source labels identify the
base NGINX image, and no image signature, SBOM, or provenance attestation was
found. Republish it through the approved CI path before one-seat live
certification. Launchpad builds the Showroom from the immutable Git content
revision above; it does not package each guide into a separate participant-
content image.

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

1. Republish the presentation with correct OCI labels, SBOM, signature, and
   provenance attestation.
2. Certify the authenticated same-origin proxy and prove that live and
   rehearsal modes cannot be confused.
3. Add and contract-test `GET /api/v1/policy`; the presentation requests it,
   but the pinned workload runtime currently exposes only the live agents and
   workflow APIs.
4. Implement `agentic-journey-telemetry-v1` correlation in the runtime.
5. Prove independent guardrail and inference outages, fail-closed behavior,
   and recovery.
6. Add certified OpenTelemetry collection and a learner-visible trace.
7. Validate namespace-scoped GitOps drift detection and pipeline evaluation.
8. Publish approved Intel Xeon latency, token, and CPU-allocation telemetry.
9. Pin immutable content provenance and complete one-, five-, and
   twenty-five-seat certification with zero-residue reclaim.

## Validation already completed

Using the repository Python 3.12 environment:

```text
Focused blueprint, catalog, onboarding, content tests: 52 passed
Full non-local backend suite: 2293 passed, 27 skipped, 13 deselected
All catalog, onboarding, and contract YAML parsed successfully
Antora Showroom build: passed without warnings
Immutable workload image manifest: resolved from Quay
Presentation unit/component/build checks: 33 passed
Presentation visual checks: 9 passed at presentation, laptop, and rehearsal widths
Immutable presentation image: built for linux/amd64 and pushed to Quay
Presentation chart contract: digest-pinned, opt-in, same-origin API proxy, and namespace-owned
git diff --check: clean
```

The 13 deselected local-runtime tests require the local Podman services and are
not failures in this change.

## Recommended next work

1. Republish the presentation from CI with correct source metadata and supply-
   chain evidence.
2. Review the 401 learning flow and commands for the intended participant
   persona.
3. Build the Showroom package and visually inspect every page.
4. Implement native journey correlation in the canonical multi-agent workload
   rather than synthesizing it in the guide.
5. Add an independently addressable guardrail boundary so failure injection
   can be tested without terminating the compact workload pod.
6. Add approved OpenTelemetry and Intel endpoint telemetry incrementally, with
   contract tests first.
7. Run one-seat certification before changing `status` or seat capacity.
