# Handoff: Red Hat and Intel agentic blueprint and 401 lab

## Current state

This working tree contains the complete candidate package for a single episodic
Launchpad journey built on the Red Hat and Intel evidence-backed multi-agent
blueprint: a Triforce-style pre-lab presentation followed by the 401 hands-on
operations lab.

The catalog pins the reviewed version 0.1.1 Showroom content to commit
`d12a47688d57b9d72fe8c069bad45cb0baad94aa`.

The presentation source is pinned to commit
`9cec3cebe7972b92385c55174674532eeb895f97` in
`jkershawrh/multi-agent-quickstart`. The Launchpad workload and Showroom
contracts remain independently pinned in the catalog item.

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
image from `multi-agent-quickstart`. It remains `status: draft` and is not
ready for participant ordering. Historical runtime receipts prove one, five,
and 25 internal seats, but those version 0.1.0 receipts do not transfer to the
revised version 0.1.1 learner journey. The exact candidate therefore returns
to a one-seat ceiling pending fresh one-seat certification.

The chart now has an opt-in presentation runtime contract. When the 401
catalog item enables it, Argo CD creates a separately owned presentation
Deployment, Service, edge Route, and ingress policy in the seat namespace. The
301 catalog item does not enable it and therefore renders unchanged.
The catalog pins that chart contract to Launchpad commit
`1a4c0349d148d1e933cfbd069b7af970054383aa`.

The live scale gates are encoded at
`certification/catalog/operate-agentic-blueprint.yaml`. One-, five-, and
25-seat internal Flightpath certification are complete for the prior immutable
runtime digest, including three consecutive 25-seat passing runs. Every gate runs
`scripts/certify-operate-agentic-blueprint-seat.sh`, which inherits the
certified 301 functional and isolation journey and additionally proves the
presentation route, live health, workflow, and read-only policy responses,
human authority boundary, and absence of a browser-visible service token. The
runtime publishes an authenticated `/api/v1/policy` description through the
presentation's same-origin server-side proxy. Certification requires HTTP 200,
the fixed `recommend_only` authority, and complete policy metadata before the
presentation may label that evidence live.

Immutable runtime artifact:

```text
ghcr.io/jkershawrh/multi-agent-quickstart@sha256:087d9548c044f1af641530f1913609715675e2eadf6dfe8c68c05bcad0cc7c86
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

The historical machine-readable post-scale audit is
[`../evidence/runs/catalog/operate-agentic-blueprint-activation-gate-audit-20260928.json`](../evidence/runs/catalog/operate-agentic-blueprint-activation-gate-audit-20260928.json).
It records `SCALE_GREEN_ACTIVATION_GATED`: internal 25-seat provisioning is
certified, public scale remains one seat, and the item remains draft. The audit
deliberately marks partial proof `AMBER` and missing proof `RED`; scale evidence
does not close a capability or production gate. The subsequent immutable
runtime release closed the same-origin live-policy and journey-correlation
gates with a 100/100 one-seat proof and zero residue:
[`../evidence/runs/catalog/operate-agentic-blueprint-flightpath-live-policy-one-seat-r2-20260928.json`](../evidence/runs/catalog/operate-agentic-blueprint-flightpath-live-policy-one-seat-r2-20260928.json).

The catalog item records these gates:

1. Prove independent guardrail and inference outages, fail-closed behavior,
   and recovery.
2. Add certified OpenTelemetry collection and a learner-visible trace.
3. Validate namespace-scoped GitOps drift detection and pipeline evaluation.
4. Publish approved Intel Xeon latency, token, and CPU-allocation telemetry.
5. Keep the historical one-, five-, and twenty-five-seat zero-residue evidence
   attached to the exact releases it tested; do not transfer it to revised
   content or runtime candidates.

The previous runtime digest earned 25-seat internal scale. Runtime source
`43889bc9444f9ef07f5b1a88e7de534af9647264` adds native correlation, keeps
the Kubernetes readiness boundary unauthenticated while workflow APIs remain
protected, and authenticates every model and semantic-classification request
with its seat-scoped key. It is
published as
`ghcr.io/jkershawrh/multi-agent-quickstart@sha256:087d9548c044f1af641530f1913609715675e2eadf6dfe8c68c05bcad0cc7c86`.
Because this is a new immutable release, historical scale evidence remains
valid only for the digest it tested. This release has now earned its one-,
five-, and 25-seat gates, including three consecutive passing 25-seat runs.

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
Published runtime policy endpoint: live, authenticated through the same-origin server-side proxy, and constrained to recommend-only authority
Presentation chart contract: digest-pinned, opt-in, same-origin API proxy, and namespace-owned
git diff --check: clean
```

Flightpath one-seat, five-seat, and 25-seat live certification are complete for runtime
digest `sha256:087d9548c044f1af641530f1913609715675e2eadf6dfe8c68c05bcad0cc7c86`.
The five-seat run created one workshop with five independently scoped
namespaces, waited for the common readiness barrier, and ran all five
participant probes concurrently. Every probe passed the seven Showroom pages,
presentation and handoff, real `granite-3.2-8b-tools` inference, semantic
routing, the three-agent workflow, live policy, correlation, guardrails, and
namespace isolation. Readiness took 276.604 seconds. Bulk reclaim took 100.18
seconds and left zero namespaces, Routes, RoleBindings, Secrets, PVCs, PVs,
Argo CD Applications, or model keys.

The first five-seat attempt is retained as RED evidence: all functional probes
passed, but the out-of-band Showroom verifier did not trust Flightpath's
private ingress CA. The GREEN rerun supplied the cluster ingress CA bundle and
scored 100/100 without disabling TLS verification. Evidence:

- `evidence/runs/catalog/operate-agentic-blueprint-flightpath-live-policy-one-seat-r2-20260928.json`
- `evidence/runs/catalog/operate-agentic-blueprint-flightpath-live-policy-five-seat-r1-20260928.json`

The current authenticated and correlated runtime then completed three
consecutive 25-seat GREEN-live runs. Runs `r2`, `r3`, and `r4` each passed all
25 participant probes and scored 100/100. Their readiness times were 1251.055,
1304.43, and 1231.743 seconds; cleanup completed in 171.795, 171.974, and
171.869 seconds respectively. Every run revoked its seat model keys and left
zero namespaces, Routes, RoleBindings, Secrets, PVCs, PVs, or Argo CD
Applications.

- `evidence/runs/catalog/operate-agentic-blueprint-flightpath-live-policy-twenty-five-seat-r2-20260928.json`
- `evidence/runs/catalog/operate-agentic-blueprint-flightpath-live-policy-twenty-five-seat-r3-20260928.json`
- `evidence/runs/catalog/operate-agentic-blueprint-flightpath-live-policy-twenty-five-seat-r4-20260928.json`

The previous immutable runtime's 25-seat gate is also retained as historical
evidence. A concurrent terminal-scope check exposed a
transient OpenShift API failure and was first preserved as RED evidence. A
bounded retry/backoff regression fix then completed three consecutive
GREEN-live runs (`r4`, `r5`, and `r6`), each with 25/25 participant probes,
100/100 rubric score, and zero residue. The final run reached readiness in
1186.831 seconds and reclaimed in 172.343 seconds.

- `evidence/runs/catalog/operate-agentic-blueprint-flightpath-twenty-five-seat-r4-20260928.json`
- `evidence/runs/catalog/operate-agentic-blueprint-flightpath-twenty-five-seat-r5-20260928.json`
- `evidence/runs/catalog/operate-agentic-blueprint-flightpath-twenty-five-seat-r6-20260928.json`

## Recommended next work

1. Run fresh one-seat certification for the exact version 0.1.1 Showroom
   revision, including all six stages, presentation handoff, surfaces,
   inference identity, restoration, and zero-residue reclaim.
2. Preserve the current authenticated runtime and repeat the scale gate after
   any workload, presentation, chart, model-route, or probe-contract change.
3. Add an independently addressable guardrail boundary so failure injection
   can be tested without terminating the compact workload pod.
4. Add approved OpenTelemetry and Intel endpoint telemetry incrementally, with
   contract tests first.
5. Preserve the Flightpath ingress CA as an explicit certification input; do
   not replace certificate verification with an insecure client flag.
6. Keep the catalog draft and public capacity at one until the remaining
   telemetry, failure-boundary, and production-ownership blockers are closed.
