# Showback

## What Gets Tracked

Every session produces a `ShowbackRecord` with the following fields:

| Field | Description |
|-------|-------------|
| `tenant_id` | Which tenant owns this session |
| `session_id` | Unique session identifier |
| `catalog_item_id` | Which catalog item was provisioned |
| `namespace` | Kubernetes namespace used |
| `duration_seconds` | Wall-clock time from provisioning to reclaim |
| `cpu_requested` / `cpu_used_estimate` | CPU allocation and estimated usage |
| `memory_requested` / `memory_used_estimate` | Memory allocation and estimated usage |
| `storage_requested` / `storage_used_estimate` | Storage allocation and estimated usage |
| `gaudi_endpoint_requests` | Number of inference requests routed to Gaudi |
| `gaudi_direct_minutes` | Minutes of direct Gaudi hardware access |
| `model_requests` | Total model inference requests |
| `estimated_tokens` | Estimated token count across all requests |
| `kafka_messages` | Kafka messages produced/consumed (if applicable) |
| `cost_estimate` | Optional simulated cost (not real billing) |

## Simulated vs Real Metrics

**MVP (current):** All metrics are simulated or metadata-based. The mock showback adapter generates records from session metadata — quota profiles, TTL, hardware profiles. No live Prometheus scraping.

**What the mock adapter does:**
- Sets `duration_seconds` from session TTL
- Sets CPU/memory/storage from the quota profile
- Estimates Gaudi usage from hardware profile
- Estimates model requests and tokens from catalog item metadata

## Future: Real Prometheus Metrics

When running on a live OpenShift cluster with the observability adapter connected:

1. **CPU/memory/storage** — scraped from namespace-scoped Prometheus metrics via `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, and PVC usage.
2. **Gaudi usage** — scraped from Gaudi device plugin metrics and gateway request logs.
3. **Model requests/tokens** — scraped from the inference gateway's `/metrics` endpoint, which tracks per-session request count, token input/output, and latency.
4. **Cost calculation** — real cost-per-token from gateway config (`cost_per_1k_tokens` per backend) multiplied by actual token counts.

## Showback Report Format

Reports can be exported as JSON or Markdown via the API:

- `GET /lab-sessions/{session_id}/showback` — returns ShowbackRecord as JSON
- Tenant summary via `ShowbackAdapter.summarize(tenant_id)` — aggregates across sessions

The ShowbackAdapter also supports `export_report(session_id, fmt)` for formatted output.

Showback is not billing. It tracks what was used and what it would cost. Real billing/chargeback is explicitly out of MVP scope.

## Intelligence Metrics

The intelligence layer tracks additional provisioning metrics via `ProvisioningOutcome` (stored in the `provisioning_outcomes` table):

| Field | Description |
|-------|-------------|
| `provision_latency_ms` | Time from request to validation complete |
| `success` | Whether provisioning + validation succeeded |
| `failure_reason` | Why it failed (if applicable) |
| `cluster_name` | Which cluster was selected |
| `hardware_profile` | Which hardware was used |

These feed into the FeedbackTracker for success rate computation and the ProvisioningAnalytics admin page.
