# September 17 internal pilot status — September 9, 2026

## Decision

The automated exact three-workshop gate is **GREEN-live for a supervised
internal pilot**. Three independently provisioned event topologies have passed,
the exact topology completed a 60-minute soak, and the latest run reclaimed
with zero residue. It is **not production or GA certified** because manual
frontend acceptance, public access, dependency triage, and per-seat LiteLLM
attribution remain separate gates.

The successful rehearsals used three staggered 25-seat orders and then ran all
75 participant journeys with overlap. The September 9 run also reproduced 25
simultaneous participant-created Routes while Multi-Agent traffic was active:

| Workshop | Cluster | Functional result |
|---|---|---:|
| Building an AI Agent | Brutus, controlled by Arena | 25/25 |
| Multi-Agent Quickstart | Arena | 25/25 concurrent plus 25/25 deep checks |
| Serve LLMs | Arena | 25/25 grounded RAG responses |

All 75 seats were reclaimed. Final inspection found zero run namespaces and
zero Argo CD Applications on either execution target. Brutus was contacted only
through the Arena backend's persisted remote client. The default kubeconfig
context was never changed.

## Proof strategy

- **TDD:** cleanup finalizer, workshop-wide expiry, aggregate TTL reclaim,
  interrupted lifecycle repair, terminal seat normalization, and model metrics
  network access were introduced as failing tests before implementation.
- **EDD:** the exact run, resilience window, cleanup result, image digests,
  workshop IDs, cluster assignments, participant results, and hashes are stored
  under `evidence/runs/` without plaintext credentials.
- **CDD:** the catalog certification contract, workshop/session APIs,
  observability API, Prometheus metric names, and GitOps manifests are covered
  by provider/consumer tests.
- **BDD:** three orders were retained, all participant journeys ran, namespace
  isolation was enforced, and group reclaim left zero residue.
- **CBT:** catalog journeys, Showroom, terminal scope, policy rollback, model
  output, lifecycle reconciliation, admin read model, and Prometheus discovery
  were tested independently before the combined decision.

## Red/green matrix

| Gate | State | Evidence |
|---|---|---|
| Staggered three-order provisioning | GREEN-live | Three distinct 25-seat workshops reached Ready on their persisted targets |
| Participant functionality | GREEN-live | 75/75 catalog-specific journeys passed |
| Namespace isolation | GREEN-live | Tested identities could edit their own namespace and were denied cross-namespace and node access |
| Real LLM behavior | GREEN-live | Multi-Agent and grounded RAG calls completed under the combined load |
| Bulk reclaim | GREEN-live | 75/75 sessions reclaimed; zero run namespaces and Applications remained |
| Workshop-wide TTL contract | GREEN-local | Every seat uses one order expiration and TTL enforcement reclaims the workshop as a group |
| Interrupted lifecycle repair | GREEN-local/live | Partial and terminal child-state contradictions have regression coverage; the historical false in-flight row was repaired live |
| Showroom namespace-owned cleanup | GREEN-live | One-seat rerun passed 100/100 with zero residue and no Showroom finalizer recovery |
| Launchpad metrics scrape | GREEN-live | Arena user-workload Prometheus reports the backend target `up=1` |
| vLLM and TEI scrape | GREEN-live | Two vLLM targets and one TEI target report `up=1`; vLLM request metrics are queryable |
| Arena node/network resilience | GREEN-live-after-RED | Supported 30-second ingress reload coalescing prevented router restarts during 25-Route churn; the exact driver now fails on any restart increase |
| 60-minute concurrent soak | GREEN-live | 3,613 seconds, 51/51 samples, 75/75 Showrooms each sample, zero readiness/model failures, and no restart increase |
| Manual requester/participant frontend | RED-pending | Scheduled for the next-day manual acceptance session |
| Public browser/SSO access | DEFERRED | Separate infrastructure and browser certification stream |
| Three exact functional rehearsals | GREEN-3-of-3 | Three successful exact 75-participant runs are recorded; run 3 retained immutable RED-to-GREEN ingress evidence |

## Pilot rubric

The automated internal functional rubric scores **100/100**:

| Category | Points |
|---|---:|
| Contract and immutable evidence | 15/15 |
| Placement and aggregate capacity | 15/15 |
| Provisioning and readiness | 20/20 |
| Participant functionality and LLM behavior | 25/25 |
| Authorization and isolation | 15/15 |
| Cleanup repeatability | 10/10 |

The automated score does not turn this into a GA declaration. Manual visual
acceptance is intentionally not inferred from API and browser probes, public
access has its own infrastructure/SSO certification, per-seat model telemetry
is incomplete, and the repository dependency findings still require triage.

## Deployed observability

Arena now runs the versioned Launchpad ServiceMonitor, lifecycle recording and
alert rules, and the Grafana dashboard ConfigMap. OpenShift user-workload
Prometheus is scraping Launchpad, vLLM, and TEI. The authenticated admin API
returns `launchpad.admin-observability/v1` and currently reports zero active or
in-flight lab seats after cleanup.

Arena has no approved standalone Grafana instance, so the dashboard remains
dashboard-as-code plus OpenShift Observe queries. Direct workshop-to-LiteLLM
traffic is not yet normalized into per-seat request, error, rate-limit, and
token attribution; unavailable data must stay visibly unavailable rather than
render as zero.

## Tomorrow's manual frontend acceptance

Run one internal order from the requester portal and prove, in one browser
journey:

1. capacity preview, order confirmation, and selected cluster display;
2. workshop and seat progress in the requester and admin views;
3. **Open Lab** reaches the correct Showroom content;
4. terminal starts in the assigned namespace;
5. the complete catalog-specific learner journey works;
6. admin observability follows provisioning, in-flight, and resolution states;
7. manual reclaim is idempotent and leaves zero namespace, Application,
   RoleBinding, Route, Secret, storage, and model-key residue.

Public access is not part of this manual internal acceptance unless its separate
DNS/tunnel and SSO prerequisites are intentionally enabled.

## Remaining path after automated certification

1. Run the planned requester, participant, lab, and admin visual acceptance in
   one browser journey; do not infer this result from API probes.
2. Route participant inference through a version-pinned, security-reviewed
   LiteLLM proxy and live-certify per-seat outcomes, tokens, rate limits, and
   latency. The stable virtual-key/session/seat correlation and admin display
   contract are GREEN-local; Arena still uses direct OVMS/vLLM endpoints.
3. Triage the current dependency findings before any production/GA decision.
4. Complete the separate public ingress/SSO browser certification after the
   DNS/tunnel path is approved.
5. Keep `rhgnr1` cordoned outside supervised provisioning and participant test
   windows; the runbook should uncordon it only after Ready/pressure preflight.

## Serve LLMs Showroom revision — GREEN-live

Catalog `intel-llm-cpu-serving` version `1.0.3` now points to the immutable
`pilot-2026-09-17-intel-llm-cpu-serving-v1.0.3` tag. A fresh Arena seat cloned
that exact tag and rendered the bounded participant-facing `/api/ping` Route
readiness loop. The deployed AnythingLLM route returned HTTP 200, the grounded
RAG certification returned the expected source-backed fact, and reclaim left no
namespace or Argo CD Application. See
`evidence/runs/intel-llm-cpu-serving-v103-live-20260909.json`.
