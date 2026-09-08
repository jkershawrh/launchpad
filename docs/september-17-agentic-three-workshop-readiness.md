# September 17 agentic three-workshop readiness gate

## Approved event outcome

On **September 17, 2026**, Launchpad must support three separate 25-seat
workshop orders. Provisioning is staggered, but all 75 participant seats must
remain usable concurrently.

AgentOps has been replaced in this event candidate by
`multi-agent-quickstart`. AgentOps remains available as a five-seat pilot; its
prior readiness contract and RED 25-seat capacity evidence remain immutable.

| Provision order | Catalog item | Seats | Current evidence | Candidate target |
|---|---|---:|---|---|
| 1 | `multi-agent-quickstart` | 25 | GREEN-live-25 three consecutive times on Arena | Arena |
| 2 | `intel-llm-cpu-serving` | 25 | Current tagged content GREEN-live at five seats; GREEN-live-25 historically on Arena | Arena |
| 3 | `intel-xeon6-agent-201` | 25 | Current compact release passed one internal 25-seat run on Brutus | Brutus |

The order is **Multi-Agent first**, Serve LLMs second, and Building an AI
Agent third. The Multi-Agent workshop has the longest measured provisioning
time, so starting it first preserves the most recovery time. Do not submit the
next order until every seat in the preceding workshop is Ready. Do not reclaim
an earlier workshop while creating the next one.

The approved event topology uses **two execution clusters**. Arena hosts two
complete workshops and Brutus hosts one. Every workshop retains whole-workshop
affinity: its 25 seats stay together on the named cluster and are never split
or silently moved. Event orders use an explicit admin target override so the
evidence cannot accidentally describe a different placement. Arena is enabled;
Brutus remains fail-closed until its repeat/soak gate passes. Oberon is excluded
from event execution until its capacity and namespace-deletion defects are
remediated.

## Why this substitution is materially safer

The old event candidate required 25 AgentOps seats. That workload is proven at
five seats but its 25-seat reservation cannot fit on the currently qualified
Arena worker topology with protected headroom. The replacement Multi-Agent
workshop uses shared model serving and reserves two seat pods instead of the
12 steady seat pods required by the optimized AgentOps candidate.

Multi-Agent catalog v0.2.5 has three consecutive 25-seat GREEN-live runs. In
each run, every seat opened its Showroom pages, used its participant UI, ran
the three-agent workflow against a real model, exercised MCP and guardrails,
applied and rolled back the Track 2 learner policy, proved namespace isolation,
revoked its model key, and reclaimed with zero residue.

## Revised capacity contract

| Workshop | CPU | Memory | Pod slots | Declared seat storage |
|---|---:|---:|---:|---:|
| Multi-Agent, 25 seats | 30,000m | 51,200 MiB | 50 | 0 GiB |
| Serve LLMs, 25 seats | 16,625m | 37,200 MiB | 50 | 0 GiB |
| Building an AI Agent, 25 seats | 10,375m | 22,800 MiB | 75 | 0 GiB |
| **Event total** | **57,000m** | **111,200 MiB** | **175** | **0 GiB** |

With 20 percent workload headroom, the admission target is 68,400m CPU,
133,440 MiB memory, and 210 pod slots.

The approved placement distributes that reservation as follows:

| Cluster | Workshop | Declared pods | Pods with 20% headroom | Declared CPU / memory |
|---|---|---:|---:|---:|
| Arena | Multi-Agent + Serve LLMs | 100 | 120 | 46,625m / 88,400 MiB |
| Brutus | Building an AI Agent | 75 | 90 | 10,375m / 22,800 MiB |

The September 7 read-only inspection measured 284 available pod slots, 335,259m
CPU, and 1,279,531 MiB memory on Arena. The aggregate Arena capacity envelope
requires 120 protected pod slots, 55,950m CPU, and 106,080 MiB memory. Brutus
reported 141 available pod slots against the 90-slot protected Agent 201
envelope. These measurements make the topology eligible for staged live
certification; they are not functional evidence. Current free capacity on every
target must be measured live immediately before every rehearsal and event
order. Admission must fail closed if active pod count, requested CPU or memory,
node readiness, workload-start canaries, model health, image availability,
storage, ingress, credentials, or temporary rollout demand do not fit the
protected envelope.

## Evidence boundary

The earlier Arena pilot in
`evidence/arena-staggered-three-workshops-2026-09-04.json` proved the platform
shape: three staggered 25-seat orders, 75 retained participant environments,
concurrent functional use, authorization isolation, and zero-residue reclaim.
It included Serve LLMs and Building an AI Agent, but used LLM Tool Calling as
the third workshop.

The Multi-Agent promotion in
`evidence/multi-agent-quickstart-25-seat-promotion-2026-09-06.json` proves its
current 25-seat release independently. These results make the revised exact
trio eligible for rehearsal; they do not replace the exact combined proof.

Public access is not certified for this event candidate. The first rehearsal
uses internal/VPN access so public DNS, Cloudflare quick-tunnel lifetime,
Keycloak, and Console OIDC cannot be confused with workload-scale results.

## Exact-trio run 01 — RED

Run 01 proved that the three exact orders can be provisioned in sequence and
retained together: Multi-Agent reached 25/25 Ready in 768 seconds, Serve LLMs
reached 25/25 in 679 seconds, and Building an AI Agent reached 25/25 in 375
seconds. There were no provisioning failures.

The run is nevertheless **RED and not certified**. During the first concurrent
participant probes, two Multi-Agent routes failed and `rhgnr1` became NotReady
amid cluster connectivity outages. Workload placement was highly concentrated
on that worker (240 active pods versus 66 on `gnr2`), and the single backend
and Postgres replicas were also on `rhgnr1`. Participant testing and the
60-minute soak were stopped after the critical failure.

Cleanup provided useful recovery evidence. Building an AI Agent and Serve LLMs
reclaimed normally. Multi-Agent reclaim paused when the backend and Postgres
became unavailable, then resumed automatically from persisted state after the
services recovered. All three workshops finished with 75/75 seats reclaimed,
zero failed reclaims, zero remaining run namespaces, and zero remaining Argo CD
Applications. The immutable record is
`evidence/september-17-agentic-trio-run01-red-2026-09-06.json`.

Before run 02, GitOps pins the singleton backend, Postgres, and resource
reconciler to stable `gnr2`; the reliability alert includes Postgres; and every
event catalog excludes a worker that has been Ready for less than 15 minutes.
Each seat namespace is also assigned round-robin to an eligible stable worker,
so its Showroom and workload pods cannot all fall onto the scheduler's current
favorite node. Run 02 must still prove all 75 participant journeys, namespace
isolation, real LLM traffic, and the full 60-minute concurrent soak. The
control-plane pin and seat spreading are recovery guardrails, not evidence that
the two-worker Arena execution capacity is itself stable.

## Exact-trio run 02 — RED

Run 02 proved that node spreading works: Multi-Agent reached 25/25 Ready in
about 543 seconds and distributed its seat namespaces 13 on `gnr2` and 12 on
`rhgnr1` (26 and 24 active seat pods respectively). The first workshop was
retained while the Serve LLMs capacity preview passed.

The run stopped during the second order. The backend exceeded its original
512Mi limit and was OOMKilled. After the live memory increase, two new Showroom
pods assigned to `rhgnr1` did not make deterministic startup progress even
though the node still reported Ready. Building an AI Agent was therefore never
ordered, and no participant, isolation, real-LLM, or soak gate was attempted.

Cancellation exposed a second control-plane race: the backend replacement
overlapped workshop recovery, and two Serve LLMs sessions arrived after the
workshop had already completed reclaim. The scheduled reconciler also could
not reach PostgreSQL because its standalone pod did not match the rendered
database ingress policy. Targeted normal session reclaim removed both late
sessions. Final verification found zero run namespaces and zero Argo CD
Applications, but automatic cleanup remains RED because manual reconciliation
was required. The immutable record is
`evidence/september-17-agentic-trio-run02-red-2026-09-06.json`.

Before run 03, deploy the 1Gi/2Gi backend envelope, Recreate rollout strategy,
persisted stop-state check, late-session reconciler, fail-closed persistence,
and reconciler NetworkPolicy label. Then prove the scheduled reconciler can
reach PostgreSQL and repair or exclude `rhgnr1` using a workload-start canary;
the Kubernetes Ready condition alone did not predict usable seat startup.

The run-02 remediation was deployed and verified separately at Argo revision
`ea27316` with backend build 110. Detailed database, Kubernetes, catalog, and
model API health passed; a fresh reconciler job reached PostgreSQL with zero
errors; and both run-02 workshop selectors still returned zero namespaces and
zero Argo CD Applications. This makes the remediation **GREEN-live**, while
the failed run and the event release decision remain RED pending run 03. See
`evidence/september-17-agentic-trio-run02-remediation-2026-09-06.json`.

## Approved two-cluster topology after run 02

Runs 01 and 02 remain immutable all-Arena RED evidence. They proved valuable
orchestration and recovery behavior, but they do not certify the newly approved
fleet topology.

The candidate assigns both Multi-Agent and Serve LLMs to Arena, and Building an
AI Agent to Brutus. Arena already has three consecutive current Multi-Agent
25-seat passes and historical Serve LLMs 25-seat evidence. Brutus has one
current internal 25-seat Agent 201 pass in
`evidence/brutus-agent-201-three-pod-certification-2026-09-05.json`, but still
needs its repeat/soak gate.

Oberon is not an event execution target. Its live Serve LLMs preview reported a
safe maximum of 19 seats rather than the required 25. Two one-seat portability
runs were reclaimed in Launchpad, but their empty namespaces remained
`Terminating`. Namespace conditions identify stale
`subresources.kubevirt.io/v1` and `v1alpha3` discovery plus a missing
`openshift-cnv/hco-webhook-service` conversion endpoint. Launchpad will not
force-remove namespace finalizers or claim zero-residue cleanup while that
cluster-level defect remains.

The current topology contract is recorded in
`evidence/september-17-two-cluster-three-workshop-readiness-2026-09-07.json`.
Its status is RED until all target gates and the exact combined rehearsal pass.

Validate the immutable request shape without contacting a cluster:

```bash
./scripts/september_17_multicluster_preflight.py --contract-only
```

After Brutus has passed its activation gate, run the read-only live preview through the
Launchpad API. The command submits no order and creates no cluster resource:

```bash
LAUNCHPAD_ADMIN_API_KEY="${LAUNCHPAD_ADMIN_API_KEY}" \
  ./scripts/september_17_multicluster_preflight.py \
  --api-base-url https://launchpad-api.apps.arena.fm2aihpcsed.com \
  --output evidence/runs/september-17-multicluster-preflight.json
```

GREEN requires all three previews to return `can_provision: true`, preserve the
exact Arena, Arena, and Brutus assignments, and fit the aggregate per-cluster
reservation. A disabled or unreachable target, insufficient capacity, or any
placement substitution keeps the gate RED.

### Two-cluster capacity inspection — GREEN; functional gate — RED

The 2026-09-07 live, non-mutating inspection reached Arena and Brutus through
the Arena control plane. Both individual Arena 25-seat previews passed, and
their combined protected reservation fits the measured free CPU, memory, and
pod slots. Brutus also has enough measured headroom for its protected 25-seat
envelope, but its preview remains fail-closed while placement is disabled.

This is capacity evidence only. It does not prove 50 retained Arena participant
journeys, the Brutus repeat/soak, or the exact 75-seat rehearsal. The overall
result therefore remains **RED**.

### Tagged Serve LLMs one-seat canary — GREEN-live

The current `intel-llm-cpu-serving` 1.0.1 catalog and pinned September content
completed a clean one-seat Arena canary on September 7. Showroom and the guide
returned HTTP 200, the terminal opened in the assigned namespace, its service
account could edit that namespace but could not read `default`, and all four
short-lived LiteMaaS runtime fields were present behind the namespace-scoped
Secret boundary. The participant deployed AnythingLLM from the Showroom
terminal and completed the deterministic Orion leave-policy RAG journey with
HTTP 200, the exact fact, and its source citation in 4.100597 seconds.

The first certification attempt was RED because its driver still expected to
scrape the participant API key from rendered Antora HTML. Secrets are
intentionally excluded from Antora and Argo CD. A failing contract test now
locks that boundary, and the corrected driver reads the runtime Secret through
the Showroom service account without publishing the key. Reclaim reached zero
namespaces, Routes, Applications, RoleBindings, pods, and Secrets in under ten
minutes. The immutable record is
`evidence/runs/intel-cpu-serving-one-seat-arena-20260907.json`.

The one-seat record proves only that scope. The five-seat run described next
adds simultaneous deterministic RAG journeys and bulk reclaim before the
retained Arena Multi-Agent 25 + Serve LLMs 25 rehearsal.

### Tagged Serve LLMs five-seat gate — GREEN-live

The current release then completed the five-seat Arena gate at deployed Git
revision `8cb4207`. All five seats reached Ready in 56.189972 seconds from
workshop start, every Showroom and guide returned HTTP 200, every terminal
opened in its assigned project, all own-namespace edit checks passed, and all
five cross-seat reads were denied. The ten participant pods contained 20 ready
containers with zero restarts.

All 20 simultaneous deterministic RAG calls across four bursts returned the
exact fact and source citation. The first burst preserved a RED performance
observation at 10.900942 seconds nearest-rank p95. The next three consecutive
bursts passed the existing under-10-second criterion at 8.861017, 6.673436,
and 7.777173 seconds. Normal workshop reclaim removed all five sessions, and
the namespace and Application counts reached zero in 83 seconds with no forced
finalizers. The immutable evidence is
`evidence/runs/intel-cpu-serving-five-seat-arena-20260907.json`.

The current-release one- and five-seat gates are complete. They do not certify
25 current seats or aggregate coexistence with Multi-Agent.

### Retained Arena 25 + 25 attempt — RED-live

The September 7 retained attempt reached Multi-Agent 25/25 and recovered Serve
LLMs from 16 ready plus nine failed seats to 25/25 in the same workshop. The
bounded model-preflight retry and clean retry-state contracts are GREEN-live.
The participant and platform gate is not: the first simultaneous 25-seat CPU
RAG burst returned 22 grounded, cited answers and three connection resets. A
repeat immediately returned eleven HTTP 503 and fourteen HTTP 500 failures.

During the same interval, `rhgnr1` entered NotReady for the second time in less
than 25 minutes despite low CPU and memory utilization and no resource-pressure
conditions. Probe failures affected participant workloads, model routing,
Launchpad, Keycloak, and multiple OpenShift operators. The backend still
reported 50 ready sessions while only 30 workshop namespaces remained visible,
17 of them Terminating. This lifecycle drift also keeps the gate RED; its
initiator must be proven from audit evidence before rerun.

The immutable run record is
`evidence/runs/september-17-arena-retained-25x2-20260907-node-instability-red.json`.
Arena must not be advertised for two concurrent 25-seat workshops until the
worker/runtime/network cause is repaired and the entire retained participant,
isolation, soak, and zero-residue matrix passes. The preferred event path is one
25-seat workshop per independently stable execution cluster. If only Arena and
Brutus are available, the remaining options are a repaired Arena 50-seat gate
or onboarding a third execution cluster; Oberon remains excluded.

## Exact-trio GREEN-live procedure

1. Record commit SHA, catalog versions, image digests, model routes, target
   credentials, node conditions, active pods, requested resources, and
   admission output for Arena and Brutus.
2. Submit Multi-Agent 25 with the explicit Arena override and wait for all 25
   seats to cross the common readiness barrier.
3. Submit Serve LLMs 25 with the explicit Arena override, wait for all seats,
   and retain Multi-Agent.
4. Submit Building an AI Agent 25 with the explicit Brutus override, wait for
   all seats, and retain the other 50 environments.
5. Start the 60-minute concurrent hold only when all 75 seats are Ready.
6. Exercise all 75 participant journeys concurrently. Validate Showroom,
   terminal namespace identity, workspace UI, real LLM output, required tools,
   and cross-seat and node denial.
7. Capture shared model request latency, queue depth, failures, and HTTP status
   during the concurrent burst. A running pod is not functional evidence.
8. Reclaim one workshop at a time and verify model-key revocation plus zero
   remaining namespaces, Routes, RoleBindings, PVCs/PVs, Secrets, and Argo CD
   Applications belonging to the run.
9. Repeat the exact trio. Any discovered defect first becomes a failing test
   and RED evidence before correction and rerun.

## Red/green matrix

| Gate | RED baseline | Required GREEN-live evidence |
|---|---|---|
| Exact catalog revisions | Prior proofs span different revisions and workshop combinations | All three orders record the pinned event revisions and digests |
| Capacity | Individual Arena previews pass and the aggregate protected envelope fits; Brutus remains intentionally disabled | Brutus activation plus per-cluster aggregate preview and revalidation immediately before each order |
| Provisioning | No exact two-cluster trio has run together | 25 + 25 on Arena and 25 on Brutus Ready through targeted staggered orders |
| Functional behavior | Pod readiness alone proves nothing | 75 participant journeys complete with real model responses |
| Authorization | Combined-run isolation is not yet recorded | Every seat can edit only its assigned namespace; cross-seat and node access are denied |
| Soak | No exact-trio 60-minute hold | All seats and model routes remain healthy for 60 minutes |
| Cleanup | Exact revised trio has not been reclaimed | Every generated resource and model key is gone with zero residue |
| Public access | Public access is not certified | Remains out of scope for the internal event rehearsal |

## Release rubric

The event candidate requires 100/100: 15 points for immutable contracts and
artifacts, 15 for placement and capacity, 20 for provisioning/readiness, 25
for participant functionality, 15 for authorization/isolation, and 10 for
cleanup and repeatability. Any failed critical cell keeps the event candidate
RED regardless of the numerical score.

The read-only two-cluster capacity inspection and the current tagged-content
Serve LLMs one- and five-seat certifications are complete. The next gates are
the retained Arena 25 + 25 functional run and the remaining Brutus Agent 201
repeat/soak. Enable Brutus for event
orders only after its workload gate passes, then repeat the exact preview and
combined 75-seat rehearsal. AgentOps continues separately at a maximum of five
internal seats until its own 25-seat capacity and architecture gates are
satisfied.

## September 8 exact functional rehearsal — GREEN-live / RED-resilience

The later exact rehearsal supersedes the pending functional statements above
without rewriting the immutable earlier RED records. Three staggered 25-seat
orders reached Ready on the approved topology: Multi-Agent and Serve LLMs on
Arena, and Building an AI Agent on Brutus through the Arena backend. All 75
participant journeys then passed with overlap. This is stricter functional
load than the event's intended one-workshop-at-a-time participant use.

Sequential reclaim completed for all 75 seats with zero run namespaces and
zero Argo CD Applications remaining. The observed Showroom finalizer fallback
became a failing regression test. A subsequent one-seat run at commit
`0a42971` proved namespace-owned Showroom cleanup with a 100/100 catalog rubric,
zero residue, and no Showroom finalizer recovery.

The exact run remains RED for production resilience: Arena recorded correlated
probe pressure and retryable connection resets, the successful run did not
include a 60-minute soak, and it is only the first exact GREEN-functional run.
The requester/participant frontend journey is reserved for manual validation
on September 9. Public access remains a separate gate.

The current decision and validation matrix are in
`docs/september-17-pilot-status-20260908.md`. The immutable run evidence is
`evidence/runs/september-17-exact75-functional-green-resilience-red-20260908.json`
and
`evidence/runs/september-17-exact75-cleanup-green-finalizer-warning-20260908.json`.
