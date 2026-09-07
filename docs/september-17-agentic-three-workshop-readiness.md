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
| 2 | `intel-llm-cpu-serving` | 25 | GREEN-live-25 on Arena | Arena |
| 3 | `intel-xeon6-agent-201` | 25 | Earlier Arena 25-seat pass; current compact release passed 25 on Brutus | Arena, with a current-release regression |

The order is **Multi-Agent first**, Serve LLMs second, and Building an AI
Agent third. The Multi-Agent workshop has the longest measured provisioning
time, so starting it first preserves the most recovery time. Do not submit the
next order until every seat in the preceding workshop is Ready. Do not reclaim
an earlier workshop while creating the next one.

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

The Arena snapshot taken on September 6/7 observed two schedulable workers,
500 total worker pod slots, and 216 active worker pods. Holding 20 percent of
worker pod capacity in reserve leaves **184** additional slots. The event's
175-slot reservation therefore fits that snapshot with only nine slots left
inside the protected ceiling.

This is intentionally a narrow **candidate**, not a capacity guarantee. The
current free Arena capacity must be measured live immediately before every
rehearsal and event order. Admission must fail closed if active pod count,
requested CPU or memory, node readiness, model health, image availability, or
temporary rollout demand no longer fits the protected envelope.

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

## Exact-trio GREEN-live procedure

1. Record commit SHA, catalog versions, image digests, model routes, Arena node
   conditions, active pods, requested resources, and admission output.
2. Provision Multi-Agent 25 and wait for all 25 seats to cross the common
   readiness barrier.
3. Provision Serve LLMs 25, wait for all seats, and retain Multi-Agent.
4. Provision Building an AI Agent 25, wait for all seats, and retain the other
   50 environments.
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
| Capacity | Point-in-time margin is only nine protected pod slots | Preflight and revalidation pass immediately before each order |
| Provisioning | No exact revised trio has run together | 25 + 25 + 25 Ready through staggered orders |
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

The next gate is **Arena stability validation followed by exact-trio run 02**.
AgentOps continues separately at a maximum of five internal seats until its
own 25-seat capacity and architecture gates are satisfied.
