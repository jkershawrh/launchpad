# Pilot issue and feature register

This is the authoritative working backlog for defects, operational risks, and
product improvements discovered during the September 17 pilot. Dated evidence
files remain the proof of what happened; this register records what still needs
to change.

## How to use this register

- **Open** means no safe durable correction has been proven.
- **Mitigated** means the participant path is protected by a temporary patch,
  guard, retry, or operating procedure. It is not closed.
- **Deferred** means the item is intentionally outside the current pilot gate.
- **Verified** means the durable correction passed its required automated,
  participant-facing, and cleanup evidence. Verified items may be moved to a
  dated release record after the event.
- Every newly observed defect must receive an ID and a reproducible failing
  test before implementation. Closure requires the proof named in the item.
- Never edit historical evidence to make an open item appear green.

Owners and target releases should be assigned during backlog triage. Severity
uses `S0` for event-stopping, `S1` for participant-critical, `S2` for degraded
operation, and `S3` for improvement work.

## Event planning and operating-model findings

### PILOT-OPS-001 — Participant count was mistaken for total seat-environments

- **Status / severity:** Open / S1
- **Observed:** initial planning treated the event as one 30-person cohort using
  three labs, or 90 seat-environments. The delivered event contained three
  30-person cohorts; every participant received all three labs and retained
  access, requiring 270 seat-environments. The additional 180 environments were
  identified and provisioned during the live event.
- **Impact:** certified Arena/Brutus capacity covered the originally understood
  event. Flightpath had been prepared as a DR candidate, not certified normal
  execution capacity, and was promoted into emergency participant service.
- **Durable fix:** require a versioned event manifest with cohorts,
  participants, assigned labs, retention, exposure, timing, model demand,
  certified execution capacity, DR reserve, and named human approvals. Display
  the calculated participant count and seat-environment count separately.
- **Proof to close:** requester and operator approve the same immutable
  manifest; the capacity preview calculates 270 for the reconstructed pilot;
  an intentionally undersized certified fleet is rejected before any seat is
  created; DR-only and uncertified capacity are excluded unless an explicit,
  audited role change passes its required gate.

## Defects and operational risks

### PILOT-BUG-001 — Cross-cluster image references break new seats

- **Status / severity:** Mitigated / S1
- **Observed:** Flightpath seats applied images hosted only in Arena's internal
  registry. Serve LLMs produced AnythingLLM `ImagePullBackOff`/503 failures;
  Building an AI Agent produced the same failure for `solution-agent`.
- **Current mitigation:** affected live deployments were patched to the approved
  Quay images and event-scoped guards restore the known-good images. The
  September 17 retained-seat inventory found and corrected 27 Brutus and one
  Flightpath `solution-agent` deployment; post-change active-seat pod readiness
  was 90/90 on Brutus and 313/313 on Flightpath.
- **Durable fix:** prohibit cluster-local registry references in promoted
  catalogs; publish signed immutable images to the approved HA registry and
  validate pullability from every eligible destination before placement.
- **Proof to close:** contract test rejects internal registry references, cold
  pulls succeed on every target cluster, and a newly provisioned workshop uses
  only recorded immutable digests without a live guard.

### PILOT-BUG-002 — Model endpoint trust is not portable across clusters

- **Status / severity:** Mitigated / S1
- **Observed:** AnythingLLM's Node client rejected the Arena model endpoint with
  `SELF_SIGNED_CERT_IN_CHAIN` when the seat ran on Flightpath.
- **Current mitigation:** active event deployments use
  `NODE_TLS_REJECT_UNAUTHORIZED=0`.
- **Durable fix:** distribute and mount the approved model-serving CA bundle,
  configure Node/OpenAI clients to use it, and remove the global TLS bypass.
- **Proof to close:** HTTPS verification succeeds from a newly provisioned seat
  with the bypass absent, invalid certificates are rejected, and certificate
  rotation passes a recovery test.

### PILOT-BUG-003 — Catalog model selection does not enforce workload capability

- **Status / severity:** Mitigated / S1
- **Observed:** `granite-2b-cpu` answered ordinary chat but returned no bytes for
  the tool-enabled streaming journey used by Serve LLMs.
- **Current mitigation:** active AnythingLLM seats were changed to
  `granite-3.2-8b-tools`.
- **Durable fix:** declare required model capabilities in the catalog and filter
  placement/model selection using a versioned capability contract.
- **Proof to close:** certification executes the exact tool-calling stream, not
  a generic chat probe, and fails placement when no compatible model exists.

### PILOT-BUG-004 — AnythingLLM state is lost during a rollout

- **Status / severity:** Mitigated / S1
- **Observed:** AnythingLLM used ephemeral storage with no volume. A pod rollout
  removed API keys, workspaces, and uploaded documents.
- **Current mitigation:** the `hr-assistant` workspace, scoped API keys, and
  embedded lab documents were recreated for active seats.
- **Durable fix:** persist participant workspace state in a PVC or approved
  external service and make initialization idempotent.
- **Proof to close:** restart and reschedule the workload during certification;
  the same API key, workspace, document metadata, and embeddings remain usable.

### PILOT-BUG-005 — Active workshops can serve a stale catalog revision

- **Status / severity:** Open / S1
- **Observed:** repository instructions and images had been corrected, while an
  already provisioned Showroom continued to apply an older revision.
- **Durable fix:** persist and display the content commit, catalog version, and
  image digests for every order; promote test revisions explicitly and never
  mutate a running workshop implicitly.
- **Proof to close:** requester, participant, and admin views show identical
  release identity; a fresh order uses the promoted release; drift detection
  reports any mismatch.

### PILOT-BUG-006 — Arena worker/network instability interrupts public access

- **Status / severity:** Open / S1
- **Observed:** `gnr2` experienced transient node/network stalls; probes timed
  out, router/cloudflared restarted, and `labs.smg-helix.ai` briefly returned a
  Cloudflare error. The node was returned to service at the event operator's
  direction after recovery.
- **Durable fix:** complete node/root-cause analysis, add sustained network and
  runtime soak evidence, and make placement respond to node degradation before
  participant traffic fails.
- **Proof to close:** the repaired node passes the agreed soak and fault test,
  active-seat traffic remains within SLO during a worker disruption, and no
  manual cordon decision is required for the tested failure.

### PILOT-BUG-007 — Public tunnel is a single failure domain

- **Status / severity:** Open / S1
- **Observed:** the named Cloudflare tunnel/router path was concentrated in one
  pod and co-located with the affected Arena worker.
- **Durable fix:** run multiple connectors with topology spread/anti-affinity,
  a PodDisruptionBudget, meaningful router health checks, and monitored tunnel
  reachability.
- **Proof to close:** deliberate pod and worker termination does not interrupt
  login, participant home, Showroom, or proxied tools.

### PILOT-BUG-008 — Fleet routing support workloads have unavailable images

- **Status / severity:** Open / S2
- **Observed:** Arena CPU/GPU endpoint picker, endpoint reconciler,
  qualification gateway, and grid publisher reported `ImagePullBackOff` because
  required internal-registry digests were unavailable.
- **Durable fix:** publish these components through the same immutable artifact
  promotion path as catalogs and add them to platform readiness.
- **Proof to close:** every required deployment is available after a cold pull
  and registry restart, and fleet readiness marks a cluster ineligible when a
  required placement component is unavailable.

### PILOT-BUG-009 — Live fixes require disruptive pod rollouts

- **Status / severity:** Open / S2
- **Observed:** changing a model, CA, or image caused a rollout; combined with
  ephemeral application state this disrupted active participants.
- **Durable fix:** separate dynamic, safely reloadable configuration from image
  releases; persist user state; define which changes require a new order.
- **Proof to close:** supported configuration changes preserve sessions and
  participant state, while unsupported live mutations fail closed.

### PILOT-BUG-010 — Event remediation guards are temporary local processes

- **Status / severity:** Mitigated / S2
- **Observed:** short-lived local guards protected active workshops from image
  and configuration regression, but they are not a durable controller and end
  with their process lifetime.
- **Durable fix:** reconcile a declared release contract in-cluster, scope it by
  workshop/catalog version, and audit every corrective mutation.
- **Proof to close:** kill/restart the controller and introduce deliberate
  drift; reconciliation resumes without changing unrelated workshops.

### PILOT-BUG-011 — StarGate misclassifies cleanup failure as informational

- **Status / severity:** Open / S2
- **Observed:** the current lifecycle publisher maps only `validation_failed`
  and `expired` to failure. A `cleanup_failed` event is emitted with
  `outcome=info`, weakening incident and residue reporting.
- **Durable fix:** use a versioned event taxonomy with typed status-to-outcome
  mapping and provider/consumer contract tests.
- **Proof to close:** producer and StarGate consumer both reject the incorrect
  mapping; deployed cleanup-failure evidence appears as failure with the same
  immutable event and correlation IDs.

### PILOT-BUG-012 — StarGate lifecycle evidence can be lost

- **Status / severity:** Open / S2
- **Observed:** webhook and Kafka publishing are best-effort. There is no
  transactional outbox, receipt ledger, replay cursor, dead-letter workflow,
  or durable visibility into undelivered events.
- **Durable fix:** implement the outbox/receipt/replay contract in
  `stargate-product-telemetry-contract.md`.
- **Proof to close:** restart, network partition, duplicate, delayed consumer,
  and incompatible-schema tests retain every event and reconcile receipts
  without blocking Launchpad lifecycle work.

### PILOT-BUG-013 — Multi-Agent UI omits authorization on agent discovery

- **Status / severity:** Open / S1
- **Observed:** Session 3 Lab 3 emitted repeated HTTP 401 responses for
  `GET /api/v1/agents` in at least two participant namespaces. The deployed
  participant UI's `fetch_agents()` call does not send `AGENT_AUTH_TOKEN`, while
  its workflow-stream call does. The same affected seat recorded HTTP 200 for
  `POST /api/v1/workflow/stream`; model, MCP, guardrail, and agent health checks
  remained successful.
- **Impact:** the agent-discovery/health panel presents an authorization failure
  and can make the participant believe the workflow itself is unavailable.
- **Durable fix:** use one authenticated orchestrator client for every protected
  UI call, including agent discovery, and render discovery failure separately
  from workflow execution state.
- **Proof to close:** component tests assert the bearer header on every protected
  endpoint; a fresh seat displays discovered agents and completes the streamed
  workflow; missing/invalid tokens still receive 401; the certified concurrent
  journey has zero unintended 401 responses.

## Performance and scale defects

### PILOT-PERF-001 — Building an AI Agent final synthesis exceeds the journey timeout

- **Status / severity:** Open / S1
- **Observed:** five sampled MCP `tools/list` calls completed in roughly 3–4 ms,
  while the full `/api/v1/advise` journey exceeded 90 seconds after a successful
  first model call and three successful MCP calls. The slow stage is the final
  LLM synthesis, not MCP discovery.
- **Near-term work:** shorten the system/custom prompt, reduce requirements and
  brief token budgets, cache static MCP results, and show stage-level progress.
- **Proof to close:** the exact participant prompt succeeds at the certified
  concurrency with recorded stage timings and acceptable p95 latency.

### PILOT-PERF-002 — The shared 8B CPU model has insufficient burst headroom

- **Status / severity:** Open / S1
- **Observed:** all active Building an AI Agent deployments correctly used
  `granite-3.2-8b-tools`. Scaling its model deployment from four toward six
  replicas admitted only a fifth; the sixth remained unschedulable because each
  replica requests 78 CPU cores. The stable event setting is five ready replicas.
- **Durable fix:** capacity-test prompt size, output budget, queue depth, timeout,
  and replica count together; reserve inference capacity per workshop and use
  a larger/different serving pool when required.
- **Proof to close:** a 30-user burst completes the complete agentic journey
  within the declared latency/error SLO without an unschedulable replica.

### PILOT-PERF-003 — Placement accounts for pods but not inference pressure

- **Status / severity:** Open / S1
- **Observed:** seat pods could be admitted even when the shared model became
  the limiting resource.
- **Durable fix:** include compatible model replicas, active/queued requests,
  token load, measured latency, and reserved workshop demand in capacity preview
  and placement eligibility.
- **Proof to close:** a capacity preview predicts an intentionally saturated
  model, rejects or queues the order before creating seats, and releases the
  reservation on reclaim.

## Product and platform features

### PILOT-FEAT-001 — Durable catalog artifact promotion

- **Status / priority:** Planned / S1
- Publish images and Showroom content once to an approved HA registry/content
  source, scan/sign them, promote immutable digests from test to production,
  pre-pull event artifacts, and retain rollback metadata.

### PILOT-FEAT-002 — Release-aware catalog CI/CD

- **Status / priority:** Planned / S1
- Build the requester-to-test-to-approval-to-production pipeline with contract,
  component, BDD, security, capacity, participant-journey, and reclaim gates.
  Produce the evidence manifest and red/green matrix for every release.

### PILOT-FEAT-003 — Inference-aware observability and admission

- **Status / priority:** Planned / S1
- Add per-seat stage state and latency, model replica pressure, token throughput,
  queue depth, retries, timeout/error class, and MCP-versus-LLM timing to admin
  observability. Tie the same signals to placement and admission.

### PILOT-FEAT-004 — Resilient public edge

- **Status / priority:** Planned / S1
- Make DNS/TLS, Keycloak, entitlement gateway, tunnel connectors, and route
  dispatch independently observable and highly available. Certify login,
  re-entry, code claim, Showroom, tools, and logout during a connector failure.

### PILOT-FEAT-005 — Participant-safe lifecycle operations

- **Status / priority:** Planned / S1
- Add drain-aware maintenance, state-preserving restart policy, workshop-scoped
  retry, owner-visible incident state, idempotent bulk reclaim, and automatic
  zero-residue verification.

### PILOT-FEAT-006 — Cluster and model qualification matrix

- **Status / priority:** Planned / S2
- Publish a versioned catalog × cluster × exposure × model limit derived from
  repeatable functional load tests. Do not publish a fleet-wide seat number
  inferred from CPU, memory, or pod capacity alone.

### PILOT-FEAT-007 — Issue/evidence integration in admin operations

- **Status / priority:** Planned / S2
- Let operators open a backlog item from a failed seat, attach session/workshop,
  cluster, catalog revision, logs, screenshots, metrics, and cleanup evidence,
  then link the verified fix back to the release manifest.

### PILOT-FEAT-008 — Product-grade StarGate evidence and product summary

- **Status / priority:** Planned / S2
- Add a versioned lifecycle envelope, durable outbox delivery, consumer receipts,
  deduplication/replay, structured logs, bounded metrics, protected traces, and
  a truthful product-list summary. Keep StarGate observe/classify/recommend
  responsibilities distinct from Launchpad mutation authority.

### PILOT-FEAT-009 — Agentic Experience Wardrobe

- **Status / priority:** Planned / S3
- Let instructors and participants select curated persona, industry, depth, and
  objective lenses over one certified lab runtime. Generate reviewable content
  with agentic AI, persist the selected profile for resume, and require human
  SME approval plus automated content/evaluation proof. Profiles that alter
  infrastructure or security become separately certified catalog profiles.

## Evidence captured during the event

- Building an AI Agent had 30/30 base Showrooms healthy and 19/19 active
  `solution-agent` deployments corrected and ready during the diagnostic pass.
- Five MCP samples completed in roughly 3–4 ms; the complete agent request then
  stalled during final LLM synthesis and exceeded the 90-second test window.
- The shared `granite-3.2-8b-tools` deployment is stable at five ready replicas;
  a sixth replica was unschedulable under its current 78-core request.
- Serve LLMs tool-enabled streaming succeeded from three corrected seats in
  roughly 0.37–0.50 seconds after selecting the compatible 8B tools model.
- These are event observations, not durable certification. Close items only
  with immutable evidence from a fresh order using the promoted release.

## Triage cadence

1. During an event, append the symptom, affected IDs, safe mitigation, and
   operator decision without rewriting earlier evidence.
2. Within one business day, reproduce the failure as a test and assign owner,
   severity, and target release.
3. Before release, update the red/green matrix, evidence manifest, support
   runbook, and canonical architecture/contract documents together.
4. After verification, record the evidence link and move the item to the dated
   release record; retain the stable ID for traceability.
