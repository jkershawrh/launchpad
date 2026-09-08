# Launchpad observability architecture

## Decision

Use a hybrid operator experience:

- The Launchpad admin frontend is the system-of-record view for current
  cluster placement, lab and workshop state, per-seat progress, failures, and
  reclaim actions. These are workflow facts owned by Launchpad, not
  infrastructure guesses.
- Prometheus and Grafana are the time-series view for resource headroom,
  provisioning and reclaim duration, network symptoms, model-serving traffic,
  latency, token throughput, and comparisons across rehearsal runs.

Do not make an operator leave Launchpad to understand or repair an order. Link
or embed the Grafana dashboard from the admin view for history and diagnosis.
Do not install a second metrics stack: Arena already runs OpenShift user
workload monitoring with two Prometheus replicas and two Thanos ruler replicas.

Arena does not currently contain a standalone Grafana or Grafana Operator.
This repository therefore ships the dashboard as code in a labeled ConfigMap.
Use OpenShift Observe for immediate PromQL validation. When the organization
selects an approved Grafana instance, import/provision the same dashboard and
connect its read-only Prometheus datasource. A new in-cluster Grafana should be
a deliberate follow-up with OpenShift OAuth, namespace-scoped RBAC, persistent
storage, TLS, and backup—not an implicit part of a workshop deployment.

## The four operational views

1. **Cluster health and capacity** — Ready nodes, CPU/memory/pod-slot
   headroom, placement enabled state, and sessions/workshops/seats assigned per
   execution cluster.
2. **Provisioning by lab and seat** — requested seats, current state, outcome,
   and aggregate provision-to-ready duration. Exact seat rows remain in the
   authenticated admin view.
3. **In-flight by lab and seat** — seats in requested, provisioning,
   validating, resetting, or reclaiming stages and time since the last
   transition.
4. **Resolution by lab and seat** — failure state, validation failures,
   reset/reclaim duration, cleanup failure, and zero-residue follow-up.

The Launchpad `/metrics` exporter rebuilds these signals from persisted
sessions, workshops, seats, and lifecycle events. Backend restarts therefore
do not reset the workflow view. The exporter intentionally does not make live
remote-cluster calls during a Prometheus scrape.

## LLM observability

### Observable now

| Layer | Current signals | Source |
| --- | --- | --- |
| Model readiness | Desired and available model deployment replicas | OpenShift kube-state metrics |
| vLLM | running/waiting concurrency, request latency, input and output token totals, cache and engine metrics exposed by vLLM | vLLM `/metrics` through `vllm-granite-tools` ServiceMonitor |
| Text Embeddings Inference | Deployment readiness only. The installed server returns HTTP 200 with an empty `/metrics` body, so request/queue/token metrics are not yet available | kube-state metrics; the `tei-nomic-embed` ServiceMonitor is staged for when metrics are enabled |
| Inference gateway | request and error counts, request latency histograms, and selected task/route/backend | `gateway_requests_total`, `gateway_request_latency_seconds`, and `gateway_routing_decisions_total` |
| Model inventory | models configured for each cluster | `launchpad_cluster_model_configured_info`; configuration only, not readiness |

Request/response success is observable at the gateway through request and
error counts. Response bodies and prompts are never metrics.

### Instrumentation gaps

- **LiteLLM rate-limit rejections:** the current gateway rate limiter returns
  HTTP 429 but does not increment a Prometheus counter, and direct LiteLLM
  traffic bypasses the gateway metrics. Add a bounded result label
  (`success`, `error`, `rate_limited`) at the authoritative proxy.
- **Exact input and output token totals:** vLLM exposes token totals, but OVMS
  and direct LiteLLM calls do not currently provide one normalized metric.
  LiteLLM callbacks or its supported Prometheus integration should be the
  normalization point.
- **TEI request and token metrics:** enable metrics in a compatible TEI build
  or add a private exporter. An empty HTTP 200 response is unavailable data,
  not a zero request rate.
- **Selected model:** Launchpad exports configured models and the gateway
  exports route/backend, but the gateway does not emit an allow-listed model
  label for every call. Do not label arbitrary client-supplied model strings.
- **Per-seat inference attribution:** virtual keys contain lifecycle metadata,
  but there is no metrics aggregation that safely joins a call to the active
  workshop and seat. Add this at the key broker/proxy boundary. Aggregate
  Prometheus data by `catalog_item` and `cluster`; keep the opaque key-to-seat
  correlation in protected logs or traces and expose the exact join only in
  the authenticated admin drill-down.
- **Response and rate-limit latency:** the current gateway histogram covers
  successful routed requests and some fallback paths, but not every early
  rejection. Instrument one outer request middleware to cover all outcomes.
- **Cross-cluster infrastructure history:** Arena Prometheus observes Arena.
  Launchpad state includes Brutus assignments, but Brutus node and network
  metrics require a read-only datasource, federation, or remote write before
  one Grafana can compare infrastructure across both clusters.

These gaps must render as unavailable, never as zero, in the admin and Grafana
views.

## Metric label policy

Allowed bounded labels are `cluster`, `catalog_item`, workflow `status`,
validation `outcome`, allow-listed `model`, and allow-listed `route`/`backend`.

No secrets, emails, API keys, prompts, responses, tenant IDs, participant IDs,
request IDs, workshop IDs, session IDs, seat numbers, namespaces, URLs, error
messages, or trace IDs may be Prometheus labels. Those values create privacy,
secret-leak, or cardinality risk over retained time series. Use the protected
admin read model for exact lab/seat state and structured logs/traces for
diagnostic correlation.

## Repository assets

- `backend/app/services/observability_metrics.py` — deterministic Launchpad
  workflow exporter.
- `deploy/launchpad/observability/service-monitor.yaml` — user-workload
  Prometheus discovery for the backend.
- `deploy/launchpad/observability/prometheus-rules.yaml` — capacity recording
  rules and lifecycle/model alerts.
- `deploy/launchpad/observability/launchpad-operations.json` — Grafana
  dashboard covering the four operational views and LLM serving.
- `deploy/models/arena/model-observability.yaml` — vLLM and Text Embeddings
  Inference ServiceMonitors in the private model namespace.

## Pilot rollout gates

1. Render and validate both kustomizations locally.
2. Deploy the Launchpad ServiceMonitor and prove the target is `up` in Arena
   user-workload Prometheus.
3. Deploy the private model ServiceMonitors and confirm the actual installed
   vLLM/TEI metric names before treating their dashboard panels as GREEN-live.
4. Exercise one provision, one validation failure, one successful reclaim,
   and one cleanup failure in a controlled test; retain PromQL and alert
   evidence.
5. Run the staggered 3x25 rehearsal and retain dashboard snapshots for the
   whole interval.
6. Add the approved Grafana datasource and import the versioned dashboard.
7. Keep public browser access certification as a separate gate.
