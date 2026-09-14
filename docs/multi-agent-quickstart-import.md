# Multi-Agent Quickstart import

## Source

Launchpad imports the lab journey from
[`jkershawrh/multi-agent-quickstart`](https://github.com/jkershawrh/multi-agent-quickstart)
at immutable revision `243870fa4675987bf77c310a53deee672a4f4af2`.
The original repository remains the application and protocol source. Launchpad
owns the Antora/Showroom participant journey in
`content-multi-agent-quickstart` so runtime identity, namespace, model, and
cluster values are rendered for each seat.

The current candidate streams the dependent Research, Analyst, and Executor
stages in execution order. The participant UI publishes each result as it
completes, records the actual model and stage duration, and retains the newest
20 runs in the current seat browser session with an explicit clear-history
action. The existing non-streaming workflow API remains compatible.

The MCP instructions use the exact tool name advertised by `tools/list`:
`search_knowledge_base`. Candidate proof, including a live three-stage model
run and MCP invocation, is recorded in
`evidence/runs/multi-agent-progressive-history-one-seat-green-live-20260914.json`.

This is a separate catalog item from the legacy `agent-swarm` visualization
and the larger `agentops-observability` workshop.

## One lab, three tracks

The catalog item preserves the three learning tracks from the upstream
quickstart inside one Showroom and one provisioned participant environment:

1. **Track 1 — Run locally:** source-guided study of the application topology,
   A2A discovery, routing, MCP, and guardrails. In Launchpad, participants use
   the pre-provisioned application rather than starting nested Docker Compose.
2. **Track 2 — Build and Operate on OpenShift:** run the live agentic workflow,
   apply a non-secret executor policy in the participant namespace, verify the
   changed behavior, and roll back cleanly. This is the certified runtime path.
3. **Track 3 — Advanced blueprint alignment:** architecture and manifest
   exploration for Kagenti, OpenTelemetry, workload identity, policy, and
   supported guardrails. Optional components are not presented as deployed
   unless the target cluster has separately certified them.

These are learning paths, not separate catalog records, seats, or model
deployments. The Showroom welcome page is the track chooser, and all tracks use
the same terminal, Workspace, namespace, and TTL.

## Launchpad seat topology

The upstream source remains immutable. Launchpad builds that exact revision,
adds model bearer-token support and a compatible pinned UI dependency, and
publishes the certification image by digest. The Launchpad-owned
`deploy/workloads/multi-agent-seat` chart runs the orchestrator, three A2A
agents, MCP server, demonstration guardrails, and Gradio participant UI as
seven containers in one workload pod. Services preserve the upstream protocol
boundaries, and separate Routes expose only the participant UI and
orchestrator. A second pod provides Showroom and its namespace-scoped terminal.

Every workload resource carries workshop, seat, session, tenant, and cluster
ownership labels. Launchpad creates a per-seat `multi-agent-runtime` Secret for
the selected model endpoint, model identifier, MaaS key, and generated service
token. The Secret is applied directly to Arena and only its name is passed to
Argo CD.

The catalog remains a fail-closed draft for production/public activation, while
its certified internal workshop ceiling is now 25 seats. The corrected runtime
first reached the functional gate after a regression retry; a second,
fresh order then reached `ready` on its first attempt without a live patch and
reclaimed with zero labeled residue. The runs are recorded in
`evidence/multi-agent-one-seat-live-2026-09-05.json` and
`evidence/multi-agent-one-seat-clean-live-2026-09-05.json`. A subsequent fresh
order proved the three-track chooser and every track page in one environment;
see `evidence/multi-agent-three-track-showroom-live-2026-09-06.json`. The
reusable framework then proved one five-seat workshop with concurrent checks on
every seat, complete isolation, and zero-residue reclaim; see
`evidence/runs/multi-agent-quickstart-5-seat-multi-agent-5seat-20260906-01.json`.
At that point they certified the shared runtime and Track 2 internal five-seat
gate, but not every optional Track 3 integration, public access, or 25-seat
scale. The later sequence below closes the internal 25-seat scale gate.

The first 25-seat attempt, `multi-agent-25seat-20260906-01`, is intentionally
retained as RED evidence and does not count toward promotion. Arena worker
`rhgnr1` stopped reporting after 24 seats were ready; the Launchpad backend,
single-replica internal registry, and both Kueue controller replicas were all
concentrated on that worker. The API returned 503, the registry temporarily had
no endpoint, and stale Kueue discovery initially blocked namespace deletion.
Persisted workshop recovery completed reclaim after the node returned, the
Kueue visibility APIs were restored, and an independent audit reached zero
residue. The generic runner now retries bounded connection and 502/503/504
failures so a transient control-plane interruption does not discard its live
observation window. See the run and fault records under `evidence/runs/`.

The second attempt, `multi-agent-25seat-20260906-02`, brought all 25 seats to
Ready and passed every participant, Showroom, agent workflow, isolation,
secret-safety, and model-key revocation check. It remains RED and uncounted
because the first residue sample ran immediately after workshop completion,
while 20 namespaces were still terminating; an independent follow-up reached
zero without intervention. The runner now polls all declared cleanup resource
types to zero within the same cleanup SLO before scoring the cleanup gate.

The third attempt, `multi-agent-25seat-20260906-03`, is the first countable
25-seat GREEN-live run. One workshop placed all 25 seats on Arena, all seats
reached Ready in 1,678.402 seconds, and ten concurrent probes verified every
Showroom track, the real three-agent workflow, namespace isolation, and secret
safety. Reclaim completed in 380.651 seconds with model keys revoked and every
declared resource count at zero. The run scored 100/100 and is pass 1 of the 3
consecutive GREEN-live runs required for 25-seat promotion. Its hashed evidence
is under `evidence/runs/`.

The fourth attempt, `multi-agent-25seat-20260906-04`, reached all 25 Ready in
777.405 seconds and reclaimed with zero residue, but is intentionally RED and
uncounted. Twenty-two seat probes passed; three probes exited with status 4
after receiving an empty/non-JSON result in the ten-concurrent remote-exec
phase. The prior runner retained only the exit status, so it could not identify
the exact failing substage. The RED→GREEN change adds bounded retries for
failed or empty remote JSON, emits a named probe stage, and persists only that
safe stage marker on failure. The failed run reset the required consecutive
25-seat promotion sequence to zero.

The fifth attempt, `multi-agent-25seat-20260906-05`, is GREEN-live after that
hardening and begins the new consecutive sequence. All 25 seats reached Ready
in 706.337 seconds, all ten-concurrent participant probes passed, and cleanup
reached zero residue in 381.098 seconds. The run scored 100/100 and is pass 1
of 3 for promotion.

The sixth attempt, `multi-agent-25seat-20260906-06`, repeated the hardened
GREEN-live result. All 25 seats reached Ready in 779.949 seconds, every
participant probe passed at ten-way concurrency, and cleanup reached zero
residue in 380.507 seconds. It scored 100/100 and is consecutive pass 2 of 3.

The seventh attempt, `multi-agent-25seat-20260906-07`, completed the promotion
sequence. All 25 seats reached Ready in 831.206 seconds, every concurrent
participant and isolation probe passed, model keys were revoked, and cleanup
reached zero residue in 381.444 seconds. It scored 100/100 and is consecutive
pass 3 of 3, making the internal 25-seat catalog limit eligible for promotion.

Catalog v0.2.5 adds a genuinely hands-on Track 2 and fixes participant UI
authentication. The first delta proof, `multi-agent-track2-learning-20260906-01`,
proved the UI bearer-token path. The next run,
`multi-agent-track2-learning-20260906-02`, is retained as RED evidence because
directly changing the Argo CD-owned Deployment was reconciled away. The final
design uses an optional, learner-owned `workflow-policy` ConfigMap instead.
`multi-agent-track2-learning-20260906-03` proved that path GREEN-live on Arena:
the learner policy changed the executor token limit from 96 to 48, the workflow
completed through the participant UI, deletion restored the 96-token baseline,
and reclaim left zero declared resources. The run scored 100/100 and its hashed
evidence is under `evidence/runs/`.

The existing 25-seat runs prove Arena topology, capacity, concurrent workflow,
isolation, and cleanup at scale. Three consecutive exact-image v0.2.5 runs,
`multi-agent-v025-25seat-20260906-01` through `-03`, then repeated the complete
25-seat workshop on Arena. Readiness completed in 727.864, 729.792, and 754.999
seconds. Across all three runs, all 75 participant probes passed the UI,
three-agent, MCP, guardrail, semantic-routing, namespace-isolation, and
hands-on policy checks. Every seat applied the 48-token override, ran the
workflow, removed the ConfigMap, and restored the 96-token baseline. Reclaim
completed in 565.917, 385.880, and 510.159 seconds with model keys revoked and
zero declared residue each time. Run 3 recorded consecutive pass 3 of 3 and
made the v0.2.5 promotion result eligible for internal 25-seat use.

## Repeatable onboarding and certification

Catalog onboarding is repository-driven rather than a collection of manual
cluster edits:

1. Change `catalog-onboarding/multi-agent-quickstart.yaml`.
2. Render `catalog/multi-agent-quickstart/catalog-item.yaml` with
   `scripts/catalog_onboarding.py render`.
3. Validate the intake, Showroom, and workload sources with
   `scripts/catalog_onboarding.py validate --fetch --build-showroom`.
4. Run the local chart and onboarding contracts.
5. Build the pinned image from the declared upstream revision.
6. Validate the reusable proof contract:
   `scripts/catalog_certification.py validate
   certification/catalog/multi-agent-quickstart.yaml`.
7. Inspect the deterministic 1-, 5-, or 25-seat plan with
   `scripts/catalog_certification.py plan`.
8. Execute `scripts/catalog_certification.py run` with an explicit Arena
   `KUBECONFIG` and the API key supplied only through the environment.
9. The generic runner calls `scripts/certify-multi-agent-seat.sh` for every
   ready namespace, then reclaims the whole workshop and records hashed
   zero-residue evidence.

## Promotion gates

1. Mirror the digest-pinned image from Arena's certification registry to a
   durable external registry or durable control-plane mirror.
2. Certify public-code participant authentication, route authorization, and
   cross-seat denial for this catalog item.
3. Certify the optional Kagenti and OpenTelemetry Track 3 integrations before
   presenting them as deployed participant services.

The internal 25-seat scale gate is complete. Production/public activation
still requires every remaining blocker above; internal scale evidence does not
certify public ingress, public identity, or a durable image supply chain.
