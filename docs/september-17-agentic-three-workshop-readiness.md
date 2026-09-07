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
| 2 | `intel-llm-cpu-serving` | 25 | GREEN-live-25 on Arena; not yet portable to Oberon | Oberon |
| 3 | `intel-xeon6-agent-201` | 25 | Current compact release passed one internal 25-seat run on Brutus | Brutus |

The order is **Multi-Agent first**, Serve LLMs second, and Building an AI
Agent third. The Multi-Agent workshop has the longest measured provisioning
time, so starting it first preserves the most recovery time. Do not submit the
next order until every seat in the preceding workshop is Ready. Do not reclaim
an earlier workshop while creating the next one.

The approved event topology is **one workshop per cluster**. Every workshop
must retain whole-workshop affinity: its 25 seats stay together on the named
cluster and are never split or silently moved. Event orders use an explicit
admin target override so the evidence cannot accidentally describe a different
placement. Arena is currently enabled; Oberon and Brutus remain fail-closed in
the registry until their target-specific gates pass.

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
| Arena | Multi-Agent | 50 | 60 | 30,000m / 51,200 MiB |
| Oberon | Serve LLMs | 50 | 60 | 16,625m / 37,200 MiB |
| Brutus | Building an AI Agent | 75 | 90 | 10,375m / 22,800 MiB |

This materially reduces the pod-pressure and worker-failure blast radius seen
in the all-Arena runs, but it is not capacity evidence. Current free capacity
on every target must be measured live immediately before every rehearsal and
event order. Admission must fail closed if active pod count, requested CPU or
memory, node readiness, workload-start canaries, model health, image
availability, storage, ingress, credentials, or temporary rollout demand do
not fit the protected envelope.

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

## Approved topology change after run 02

Runs 01 and 02 remain immutable all-Arena RED evidence. They proved valuable
orchestration and recovery behavior, but they do not certify the newly approved
fleet topology.

The next candidate assigns Multi-Agent to Arena, Serve LLMs to Oberon, and
Building an AI Agent to Brutus. Arena already has three consecutive current
Multi-Agent 25-seat passes. Brutus has one current internal 25-seat Agent 201
pass in
`evidence/brutus-agent-201-three-pod-certification-2026-09-05.json`, but still
needs its 60-minute soak and two repeat runs. Oberon has no current target-local
Serve LLMs 25-seat proof and must complete the 1 → 5 → 25 progression.

The topology contract is recorded in
`evidence/september-17-multicluster-three-workshop-readiness-2026-09-07.json`.
Its status is RED until all target gates and the exact combined rehearsal pass.

Validate the immutable request shape without contacting a cluster:

```bash
./scripts/september_17_multicluster_preflight.py --contract-only
```

After Arena control-plane authentication is restored and both remote targets
have passed their activation gates, run the read-only live preview through the
Launchpad API. The command submits no order and creates no cluster resource:

```bash
LAUNCHPAD_ADMIN_API_KEY="${LAUNCHPAD_ADMIN_API_KEY}" \
  ./scripts/september_17_multicluster_preflight.py \
  --api-base-url https://launchpad-api.apps.arena.fm2aihpcsed.com \
  --output evidence/runs/september-17-multicluster-preflight.json
```

GREEN requires all three previews to return `can_provision: true` and preserve
the exact Arena, Oberon, and Brutus assignments. A disabled or unreachable
target, insufficient capacity, or any placement substitution keeps the gate
RED.

## Exact-trio GREEN-live procedure

1. Record commit SHA, catalog versions, image digests, model routes, target
   credentials, node conditions, active pods, requested resources, and
   admission output for Arena, Oberon, and Brutus.
2. Submit Multi-Agent 25 with the explicit Arena override and wait for all 25
   seats to cross the common readiness barrier.
3. Submit Serve LLMs 25 with the explicit Oberon override, wait for all seats,
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
| Capacity | No current combined snapshot exists for all three targets | Per-cluster preflight and revalidation pass immediately before each order |
| Provisioning | No exact three-cluster trio has run together | 25 + 25 + 25 Ready through targeted staggered orders |
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

The next gate is a **read-only three-cluster preflight**. After that, certify
Oberon for Serve LLMs and finish the Brutus repeat/soak gate before enabling
either remote target for event orders. AgentOps continues separately at a
maximum of five internal seats until its own 25-seat capacity and architecture
gates are satisfied.
