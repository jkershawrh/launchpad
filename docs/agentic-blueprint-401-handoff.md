# Handoff: Red Hat and Intel agentic blueprint and 401 lab

## Current state

This working tree contains the complete candidate package for a single episodic
Launchpad journey built on the Red Hat and Intel evidence-backed multi-agent
blueprint: a Triforce-style pre-lab presentation followed by the 401 hands-on
operations lab.

The source and content candidate were committed on branch
`codex/flightpath-migration-20260922`. The catalog pins the Showroom content to
commit `ddd7c2aab25d4c10f7738f15eece1ab101a95b15`.

The converged runtime and presentation source is pinned to commit
`c2a72e7865bae7aebc913a49f91601647a95efbb` in
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
`1a4c0349d148d1e933cfbd069b7af970054383aa`.

The first live gate is now encoded at
`certification/catalog/operate-agentic-blueprint.yaml`. It permits one internal
Flightpath seat only and runs
`scripts/certify-operate-agentic-blueprint-seat.sh`, which inherits the
certified 301 functional and isolation journey and additionally proves the
presentation route, live health response, authenticated policy proxy, human
authority boundary, and absence of a browser-visible service token.

Immutable runtime artifact:

```text
ghcr.io/jkershawrh/multi-agent-quickstart@sha256:bf48f40f29b88c985adb2f6e1522dbbcdd999d2d5ff6f6911e48b2737f320767
```

Immutable presentation artifact:

```text
ghcr.io/jkershawrh/operate-agentic-blueprint-presentation@sha256:7d48b3e1c9d8dde414259add960e09bacbeb9bf7bb61013c78527b19c0c05f0b
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

The release-candidate workflow completed successfully at
https://github.com/jkershawrh/multi-agent-quickstart/actions/runs/36352732547.
Both public GHCR images are Linux/AMD64, carry the correct source and revision
labels, and have SBOM, provenance, GitHub build attestation, and keyless Cosign
signature evidence. Launchpad builds the Showroom from the immutable Git
content revision above; it does not package each guide into a separate
participant-content image.

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

1. Certify the authenticated same-origin proxy and prove that live and
   rehearsal modes cannot be confused.
2. Implement `agentic-journey-telemetry-v1` correlation in the runtime.
3. Prove independent guardrail and inference outages, fail-closed behavior,
   and recovery.
4. Add certified OpenTelemetry collection and a learner-visible trace.
5. Validate namespace-scoped GitOps drift detection and pipeline evaluation.
6. Publish approved Intel Xeon latency, token, and CPU-allocation telemetry.
7. Pin immutable content provenance and complete one-, five-, and
   twenty-five-seat certification with zero-residue reclaim.

## Validation already completed

Using the repository Python 3.12 environment and the published release-candidate
artifacts:

```text
Focused chart, content, provisioning, and access tests: 124 passed
Focused certification and contract tests: 88 passed
All catalog, onboarding, and contract YAML parsed successfully
Antora Showroom build: passed without warnings
Helm chart lint and shell syntax checks: passed
Presentation unit/component/build checks: 33 passed
Presentation visual checks: 9 passed at presentation, laptop, and rehearsal widths
Runtime and presentation images: published publicly to GHCR for linux/amd64
Runtime and presentation images: exact-digest pull and OCI source/revision labels verified
Runtime and presentation images: GitHub build attestations verified
Published runtime policy endpoint: executed successfully with recommend-only authority
Presentation chart contract: digest-pinned, opt-in, same-origin API proxy, and namespace-owned
git diff --check: clean
```

The Flightpath live gate has not run. On September 27, 2026 the stable public
gateway and its health endpoint returned HTTP 200, but the private Flightpath
API and candidate hostnames did not resolve from the operator machine. The
preflight therefore failed closed before authentication or mutation. See
`evidence/runs/convergence/operate-agentic-blueprint-flightpath-preflight-blocked-20260927.json`.

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
6. Restore private Flightpath DNS/VPN reachability, repeat the read-only
   preflight, and prove that the target has no conflicting active workshop.
7. Run one-seat certification before changing `status` or seat capacity.
