# Intel x Red Hat AI Platform Ecosystem

## Overview

Two applications form the Intel x Red Hat AI demo and operations platform. They integrate via webhook events and graceful degradation — each works standalone.

```
   +------------------+    +---------------------+
   |    StarGate      |    |     Launchpad       |   PROVISIONING + DEMO PLANE
   | Rubric evaluator |<-->| RHDP-native demos   |   Self-service AI labs on
   | Evidence bundles |    | 10 demos + 7 QS     |   shared OpenShift with
   | Failure classes  |    | Inference gateway   |   Intel Gaudi 3 / Xeon 6
   | HITL proposals   |    | Workshop batching   |
   | Provisioning     |    | Showroom content    |
   |  intelligence    |    | ArgoCD Helm chart   |
   +------------------+    +---------------------+
```

---

## The Products

### Launchpad — Portal + Demo Content

Self-service AI demo platform. Partners and customers order demos from the RHDP catalog, get isolated environments with real inference on Intel Gaudi 3 and Xeon 6, and everything cleans up automatically.

- **25 catalog items** — 10 custom Intel demos, 7 official quickstarts, 4 sandboxes, 4 originals
- **RHDP native** — provisioning via Babylon, Poolboy, Anarchy, AgnosticD, ArgoCD
- **Showroom content** — 12 AsciiDoc lab instruction pages
- **Tenant Helm chart** — per-user namespace with demo frontend + gateway + postgres
- **AgnosticV configs** — catalog item definitions for the RHDP pipeline
- **Repo:** https://github.com/rhpds/launchpad

### StarGate — Validation + Intelligence Plane

Evidence-driven rubric evaluation and provisioning intelligence. Monitors the full RHDP pipeline — Babylon, Poolboy, Sandbox API, AAP, Labigator, Demolition — and surfaces insights that improve provisioning success.

- **Runs → Stages → Evidence** pipeline for structured validation
- **YAML rubrics** define what "correct" looks like per stage
- **Failure classification** maps conditions to known failure classes
- **Provisioning intelligence** — latency tracking, root cause analysis, pool forecasting
- **HITL workflow** — AI proposes rubric changes, humans approve
- **Gated remediation** — actions routed through RHDP APIs (Anarchy, Poolboy, Sandbox API)
- **Repo:** https://github.com/rhpds/stargate

---

## Integration Architecture

### Event Flow

Both products communicate via webhook push. Each can deploy independently. When co-deployed, they form a provision-validate-monitor loop.

```
LAUNCHPAD                          STARGATE
=========                          ========

Session lifecycle events ------>  POST /integration/external-evidence
  (provisioned, ready,              |
   active, failed,                   +-- evaluates rubrics
   cleanup_failed, reclaimed)        +-- classifies failures
                                     +-- tracks provisioning latency
                                     |
Pre-flight check -------------->  GET /integration/evaluate
  (before provisioning)              |
  response: allowed/blocked          +-- constraint evaluation

                                  Cleanup result
Cleanup callback <--------------  POST /callbacks/cleanup-result

                                  Remediation action
Remediation callback <----------  POST /callbacks/remediation
  (session reset/reclaim)           (when failure escalates)
```

### Graceful Degradation

Every integration fails open. Each product works fully standalone.

| Condition | Behavior |
|-----------|----------|
| `STARGATE_API_URL` not set | Launchpad skips StarGate push, pre-flight returns `allowed=true` |
| `LAUNCHPAD_API_URL` not set | StarGate skips callback push |
| StarGate returns non-200 | Launchpad logs at debug, continues normally |
| Network error to any target | Caught, logged at debug, no impact on source |

### Shared Event Schema

```json
{
  "source": "launchpad | stargate",
  "event_type": "session.ready | evaluation_result",
  "event_id": "uuid (for deduplication)",
  "timestamp": "2026-05-26T12:00:00Z",
  "payload": {
    "session_id": "...",
    "outcome": "pass | fail | info",
    "...": "source-specific fields"
  }
}
```

### Security

- **Authentication:** `INTEGRATION_API_KEY` env var on each product. When set, inbound requests must include matching `X-API-Key` header.
- **Deduplication:** LRU cache of 10K event_ids. Duplicate events are rejected.
- **TLS:** `INTEGRATION_SSL_VERIFY` defaults to `true`. Set to `false` only for self-signed certs in dev.
- **CORS:** Configurable via `CORS_ORIGINS` env var. Explicit allowed methods and headers.

---

## Tech Stack (Aligned Across Both)

| Component | Version |
|-----------|---------|
| Python | >=3.11 |
| FastAPI | >=0.115 |
| Pydantic | >=2.10 |
| asyncpg | >=0.30 |
| httpx | >=0.28 |
| API prefix | `/api/v1/` (product routes), `/integration/` (cross-product) |
| Base image | UBI9/python-311 |
| Container tool | Podman |
| Deployment | Kustomize + AgnosticV/AgnosticD |

---

## Deployment

### Current State

| Product | GitHub | infra01 | RHDP Catalog |
|---------|--------|---------|-------------|
| Launchpad | https://github.com/rhpds/launchpad | Running | PR pending (`launchpad-demos` branch in `rhpds/agnosticv`) |
| StarGate | https://github.com/rhpds/stargate | Running | N/A (operations tool) |

### RHDP Deployment Pattern

Launchpad follows the standard RHDP pattern:

```
demo.redhat.com (user orders)
        |
        v
Babylon (orchestration)
        |
        v
AgnosticV catalog entry (common.yaml + env overrides)
        |
        v
AgnosticD playbook (workloads: keycloak, namespace, LiteLLM keys, GitOps, Showroom)
        |
        v
ArgoCD deploys tenant/bootstrap/ Helm chart
        |
        v
Per-user namespace with demo frontend + gateway + postgres
```

---

## Environment Variables Reference

### Launchpad

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | No | PostgreSQL connection. Falls back to in-memory. |
| `STARGATE_API_URL` | No | StarGate base URL for event push + pre-flight. |
| `STARGATE_API_KEY` | No | API key for StarGate authentication. |
| `DASHBOARD_AUDIT_URL` | No | Dashboard audit trail endpoint. |
| `INTEGRATION_API_KEY` | No | Required on inbound callbacks when set. |
| `CORS_ORIGINS` | No | Comma-separated allowed origins. |
| `AUTH_ENABLED` | No | `true` to enable OAuth/API key auth. |
| `API_KEYS` | No | Comma-separated valid API keys. |
| `ADMIN_API_KEYS` | No | Comma-separated admin API keys. |

### StarGate

| Variable | Required | Description |
|----------|----------|-------------|
| `STARGATE_DATABASE_URL` | No | PostgreSQL connection. |
| `STARGATE_ADMIN_API_KEY` | No | Admin API key for authenticated endpoints. |
| `STARGATE_CORS_ORIGINS` | No | Comma-separated allowed origins. |
| `STARGATE_SSL_VERIFY` | No | `false` to skip TLS verification. Default: `true`. |
| `STARGATE_LITELLM_URL` | No | LiteLLM endpoint for LLM-assisted classification. |
| `STARGATE_LITELLM_API_KEY` | No | API key for LiteLLM. |
