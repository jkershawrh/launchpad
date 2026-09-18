# Active seat inventory and reclaim observation plan

## Scope and safety boundary

This snapshot was captured at `2026-09-17T21:56Z` (`16:56 CDT`) from the
Launchpad control-plane API and the persisted target clusters. It records the
retained September 17 pilot estate, identifies conditions that could interrupt
participants, and defines how the eventual reclaim must be observed.

**No reclaim was requested or performed during this inventory.** A reclaim may
start only after explicit event-owner approval. Active workshops must never be
moved, deleted directly, or cleaned against a cluster other than their
persisted `cluster_ref`.

The image corrections recorded below occurred before the owner clarified that
this phase is backlog construction only. No further live mutation is authorized
by this document; subsequent findings are to be recorded as proposed work until
separate approval is given.

## Control-plane inventory

- Workshop records: **173 total** — **9 ready**, **164 completed**.
- Session records: **2,543 total** — **270 ready**, **2,273 reclaimed**.
- Active capacity: **nine workshops × 30 seats = 270 provisioned seats**.
- Public claims: **191 claimed**, **79 unclaimed**.
- Reconciliation: **270/270** ready session records have a matching namespace
  on their persisted cluster.
- Orphan check: **zero** managed namespaces exist without a ready session
  record on Arena, Brutus, or Flightpath.
- Public entry check: all **9/9** workshop URLs returned the expected HTTP 302
  authentication redirect.

Provisioned seats consume resources whether claimed or not. The 79 unclaimed
seats are retained event capacity, not immediately available fleet headroom.

## Post-snapshot participant-access observation

A privacy-safe, read-only correlation at `2026-09-18T13:49:44Z` found **195
active seat entitlements** across **67 pseudonymous participant identities**.
This observation appends to, and does not rewrite, the immutable `191`-claim
event snapshot above.

- Serve LLMs: **75** claims;
- Building an AI Agent: **64** claims;
- Build Multi-Agent AI Systems: **56** claims;
- **47** identities accessed all three catalog types, **10** accessed two, and
  **10** accessed one;
- **12** identities used the same-workshop claim/recovery flow more than once;
- no event activity was recorded after midnight Chicago time; the latest
  recorded activity was `2026-09-17T22:15:27Z`.

Claims and authorization checks prove access, not meaningful work or lab
completion. No email addresses were exported. The complete interpretation and
privacy boundary are retained in
[`september-17-pilot-postmortem.json`](september-17-pilot-postmortem.json).

## Workshop timeline

| Wave | Catalog | Cluster | Workshop | Created/start (UTC) | Public claims | Expiration (UTC) |
|---|---|---|---|---|---:|---|
| 1 | Serve LLMs | Arena | `d6071355` | Sep 16 03:22 | 30/30 | Sep 23 03:22 |
| 1 | Building an AI Agent | Brutus | `4876c3c0` | Sep 16 03:29 | 30/30 | Sep 23 03:28 |
| 1 | Multi-Agent | Arena | `7efa1c81` | Sep 16 03:33 | 24/30 | Sep 23 03:32 |
| 2 | Serve LLMs | Flightpath | `9d01773b` | Sep 17 16:36 | 20/30 | Sep 24 16:36 |
| 2 | Building an AI Agent | Flightpath | `7452eba7` | Sep 17 16:40 | 13/30 | Sep 24 16:36 |
| 2 | Multi-Agent | Flightpath | `fc3cab02` | Sep 17 17:08 | 13/30 | Sep 24 16:36 |
| 3 | Serve LLMs | Flightpath | `10e88065` | Sep 17 17:00 | 25/30 | Sep 24 16:36 |
| 3 | Building an AI Agent | Flightpath | `7e826ef7` | Sep 17 17:04 | 21/30 | Sep 24 16:36 |
| 3 | Multi-Agent | Flightpath | `984a4d3a` | Sep 17 17:20 | 15/30 | Sep 24 17:11 |

Full UUIDs remain in the control-plane record. Short IDs are used here for
operator readability and are not valid mutation targets by themselves.

## Runtime inventory after remediation

| Cluster | Active seats | Active-seat pods | Ready pods | Admitted Routes | Restarts recorded |
|---|---:|---:|---:|---:|---:|
| Arena | 60 | 119 | 119 | 149/149 | 142 across 23 pods |
| Brutus | 30 | 90 | 90 | 120/120 | 0 |
| Flightpath | 180 | 313 | 313 | 398/398 | 0 |
| **Fleet** | **270** | **522** | **522** | **667/667** | **142** |

The Arena restart count is historical evidence from the worker/network
instability. The affected pods are currently ready, but the restarts are
concentrated on `gnr2` and must remain a watched risk rather than being reset or
explained away.

Central model state at the snapshot:

- `vllm-granite-3-2-8b-tools`: **5/5 ready**;
- `ovms-granite-2b`: **2/2 ready**;
- `tei-nomic-embed`: **1/1 ready**.

The five optional fleet-routing/qualification support deployments remain
unavailable. The successful pilot paths do not currently depend on them, but
their state is tracked by `PILOT-BUG-008` and they must not be represented as a
healthy production routing plane.

## Safe remediation performed during inventory

The inventory found stale cross-cluster image references in already-broken
Building an AI Agent workloads:

- 27 Brutus `solution-agent` deployments were in `ImagePullBackOff`;
- one Flightpath `solution-agent` deployment was in `ImagePullBackOff` (two
  non-ready pods during its failed rollout);
- each referenced Arena's internal registry from a different cluster.

Only those affected deployments were changed. Their `solution-agent` container
was set to the previously validated immutable image:

`quay.io/redhat-gpte/triforce-solution-agent@sha256:60897d598014f040c9f515312233b5a22df80c93ba3342c16f681be027933d03`

Post-change evidence:

- Brutus active-seat pods: **90/90 ready**;
- Flightpath active-seat pods: **313/313 ready**;
- no active Brutus or Flightpath `solution-agent` deployment still references
  Arena's internal registry;
- no namespace, session, workshop, entitlement, Route, or seat was reclaimed.

This is a live mitigation for `PILOT-BUG-001`, not closure. The catalog release
and artifact-promotion pipeline must prevent recurrence in newly provisioned
orders.

## Known hiccup risks to watch

1. **Arena worker history:** 23 active-seat pods have historical restarts, with
   a maximum of 12, concentrated on `gnr2`. Do not cordon, drain, or roll these
   live workloads without an event-owner maintenance decision.
2. **Arena-local artifact dependency:** retained Arena workshops still use
   their local internal registry for current images. They are healthy because
   the images exist locally, but registry loss or a cold restart remains a
   recovery risk.
3. **Shared inference pressure:** the 8B tools deployment is healthy at five
   replicas but previously could not schedule a sixth with its 78-core request.
   Monitor queue, latency, timeouts, and retries—not only replica readiness.
4. **Building-an-Agent synthesis:** MCP calls were fast, while final LLM
   synthesis exceeded the test window under the large prompt. Shorter prompts,
   bounded output, and exact-concurrency proof remain required.
5. **Temporary event guards:** local image/model guards are short-lived
   mitigations and cannot be relied on as platform reconciliation.
6. **Functional evidence gap:** HTTP redirects, pod readiness, and admitted
   Routes do not prove every participant action. Continue representative
   synthetic and visual checks for AnythingLLM, Solution Architect, Multi-Agent,
   terminal, model, and namespace authorization paths.
7. **Multi-Agent UI authorization defect:** at `2026-09-17T22:08Z`, Session 3
   Lab 3 showed repeated 401 responses for agent discovery in at least two
   participant namespaces. The deployed UI sends its seat token for
   `/api/v1/workflow/stream` but omits it from `/api/v1/agents`. Observed workflow
   stream requests returned 200 and downstream health checks remained healthy.
   This is recorded as `PILOT-BUG-013`; no live mutation was made.

## Reclaim observation plan — do not execute without approval

The eventual reclaim is itself a certification run. It must use the Launchpad
workshop API, not direct namespace deletion, and must be captured per workshop.

### T-30 minutes: immutable pre-reclaim snapshot

- Record workshop, session, entitlement, claim, `cluster_ref`, expiration,
  reservation, catalog version, content commit, image digest, and model key.
- Count labeled namespaces, Argo CD applications, Deployments, StatefulSets,
  Jobs, Pods, Services, Routes, PVCs, ServiceAccounts, RoleBindings, and owned
  Secrets on the persisted target only.
- Capture participant-route checks, model dependency health, active lifecycle
  jobs/leases, and the current audit/event cursor.
- Hash and timestamp the snapshot. Do not store plaintext instructor codes,
  API keys, tokens, or participant email addresses in evidence.

### T0: approved lifecycle request

- Record the approver, reason, workshop UUID, request timestamp, and API request
  ID.
- Submit one idempotent workshop-level reclaim request.
- Confirm Launchpad targets the persisted `cluster_ref`; abort if it differs.
- Do not submit duplicate requests while the first durable job holds its lease.

### T+0 through T+10 minutes: lifecycle timeline

- Poll and timestamp workshop/session transitions such as `ready → reclaiming →
  completed` and every failed/retried lifecycle job.
- Record access denial, model-key revocation, RoleBinding removal, public-route
  removal, Argo application deletion, namespace deletion, and reservation
  release as separate milestones.
- At two, five, and ten minutes, record remaining resources and namespace
  deletion/finalizer conditions.
- If the ten-minute cleanup objective is missed, mark the run RED and diagnose;
  do not force-delete finalizers or retry cleanup against another cluster.

### Completion: zero-residue proof

- Require no owned namespaces, Routes, RoleBindings, PVCs, Argo applications,
  entitlements, model keys, active lifecycle jobs, or capacity reservations.
- Confirm the participant URL is denied, the workshop/session records have an
  explained terminal state, and unrelated workshops remain healthy.
- Compare actual deletion order and duration with the expected lifecycle and
  create/update a stable defect for every mismatch.
- Publish the timeline, red/green matrix cells, logs/metrics references, hashes,
  and final zero-residue result in the event evidence manifest.

## Recommended reclaim order when approval is eventually given

1. Reclaim one low-claim Flightpath workshop as the canary and prove complete
   zero residue.
2. Reclaim the remaining Flightpath workshops one at a time while observing API,
   database, queue, Argo, and cluster pressure.
3. Reclaim the Brutus workshop and verify remote-cluster cleanup.
4. Reclaim Arena execution workshops last so the active control plane is not
   competing with an avoidable local cleanup burst.

This order is a recommendation, not authorization. Expiration policy and
participant-retention commitments take precedence.
