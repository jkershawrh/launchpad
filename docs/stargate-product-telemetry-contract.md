# StarGate product telemetry and evidence contract

## Product boundary

StarGate is a shared validation, evidence, and failure-classification product
for Launchpad and future platform sources. Launchpad remains the lifecycle
authority: it owns order state, placement, credentials, authorization,
provisioning, reclaim, and mutation policy. StarGate may observe, classify, and
recommend; it cannot mutate a lab merely because it received a log event.

The initial StarGate product-list entry must describe its actual maturity:

- lifecycle evidence ingestion: **adapter exists; durable delivery pending**;
- preflight constraint evaluation: **adapter/contract exists; production gate
  pending**;
- failure classification: **planned governed capability**;
- remediation recommendation: **planned, approval-gated**;
- automatic remediation: **not certified**.

This document defines the telemetry needed to promote those statements with
evidence. It does not authorize a deployment or live integration change.

## Current implementation assessment

Launchpad currently has a webhook publisher, a Kafka publisher, mocked payload
tests, a constraint adapter, and cleanup callback tests. They demonstrate the
integration shape, not a reliable product service.

Known gaps:

1. Webhook delivery is synchronous best-effort; a failure is logged and the
   event can be lost.
2. Kafka delivery is also best-effort and has no durable application outbox,
   replay cursor, delivery ledger, dead-letter workflow, or consumer receipt.
3. The payload has no `schema_version`, aggregate sequence, request/workshop/
   seat correlation, persisted `cluster_ref`, catalog release, actor, cause,
   evidence reference, or source build identity.
4. `tenant_id` and `namespace` are accepted by the publisher but are not
   explicit payload fields. The generated `session_name` is not a reliable
   identity contract.
5. `cleanup_failed` is currently mapped to `outcome=info`, which prevents a
   truthful failure view.
6. Delivery success/failure, retry age, queue depth, and StarGate receipt are
   not exported as metrics or shown in admin operations.
7. The LLM audit buffer is process-local and capped at 1,000 entries. It is not
   a durable StarGate evidence source and estimates tokens from words.
8. Tests mock the producer boundary; there is no deployed producer/consumer
   compatibility, restart/replay, duplicate, ordering, or failure-injection
   proof.
9. Historical architecture material describes broader autonomy than is
   currently certified. The product list must use the maturity statements in
   this contract instead.

## Signal types

StarGate needs four related but distinct signal classes:

1. **Domain events** — durable facts such as order accepted, placement selected,
   seat ready, validation failed, reclaim requested, or cleanup completed.
2. **Structured operational logs** — diagnostic context for a component action,
   delivery attempt, or failure. Logs are not the lifecycle source of truth.
3. **Metrics** — bounded aggregate rates, latency, queue depth, delivery age,
   failure class, and evidence coverage. Exact identifiers are not metric labels.
4. **Traces** — protected cross-service timing for Launchpad → queue → target
   cluster/model → StarGate. Trace IDs belong in logs/traces, not Prometheus
   labels.

## Versioned event envelope

Every durable domain event must carry:

| Field | Purpose |
|---|---|
| `schema_version` | versioned producer/consumer contract |
| `event_id` | globally unique idempotency key |
| `event_type` | allow-listed domain event name |
| `occurred_at` | time the domain fact occurred |
| `recorded_at` | time Launchpad persisted the event |
| `source` / `source_version` | producer identity, commit, and release |
| `aggregate_type` / `aggregate_id` | order, workshop, session, seat, cluster, model, or reclaim job |
| `sequence` | monotonic order within one aggregate |
| `correlation_id` | joins one order/workshop operation across services |
| `causation_id` | event, request, or command that caused this event |
| `request_id`, `workshop_id`, `session_id`, `seat_number` | protected lifecycle correlation where applicable |
| `tenant_ref` | opaque tenant reference, never tenant display data |
| `cluster_ref` | immutable persisted execution target |
| `catalog_id`, `catalog_version`, `content_commit` | exact product release |
| `image_digests`, `model_refs` | bounded immutable runtime dependencies |
| `exposure_policy` | internal or public policy class |
| `status`, `outcome`, `reason_code` | typed result; no free-text metric labels |
| `duration_ms` | elapsed duration for completed stages |
| `evidence_refs` | immutable logs, metrics, trace, screenshot, or manifest references |
| `actor_type`, `actor_ref` | system, requester, participant, operator, scheduler, or remediation policy |
| `data_classification` | handling and retention class |

Namespace and exact identifiers remain protected event fields. StarGate may use
them for authorized correlation but must not expose them as public product-list
data or unbounded Prometheus labels.

## Required event taxonomy

### Order and placement

- `order.requested`, `order.accepted`, `order.rejected`;
- `capacity.previewed`, `capacity.reserved`, `capacity.released`;
- `placement.evaluated`, `placement.selected`, `placement.rejected`;
- `workshop.queued`, `workshop.provisioning`, `workshop.ready`,
  `workshop.degraded`, `workshop.failed`.

### Seat lifecycle and participant access

- `seat.provisioning`, `seat.validating`, `seat.ready`, `seat.degraded`,
  `seat.failed`;
- `access.claimed`, `access.recovered`, `access.denied`, `access.rotated`,
  `access.expired`, `access.revoked`;
- `journey.started`, `journey.checkpoint`, `journey.completed`,
  `journey.failed` with allow-listed journey/stage identifiers;
- `lab.step.started`, `lab.step.executed`, `lab.step.succeeded`,
  `lab.step.failed`, and `lab.checkpoint.completed` with stable catalog-release,
  module, step, curated-command, workshop, seat, and anonymized-participant
  identifiers plus execution source, outcome, duration, and timestamp.

An Execute-button click is not proof that a command ran. `lab.step.executed`
is emitted only after the terminal or workload execution boundary accepts the
curated action; success and failure require an observed terminal/workload
result. Curated steps carry a stable command ID or approved content digest.
Free-form terminal command text, prompts, responses, documents, credentials,
and participant email addresses are never captured by this event family.

### Runtime, artifact, and inference dependency

- `artifact.checked`, `artifact.pull_failed`, `artifact.drift_detected`;
- `route.ready`, `route.failed`, `workspace.ready`, `workspace.failed`;
- `model.admission_checked`, `model.request_completed`,
  `model.request_failed`, `model.capacity_degraded`;
- `validation.started`, `validation.passed`, `validation.failed`.

### Incident, remediation, and reclaim

- `incident.detected`, `incident.classified`, `incident.resolved`;
- `remediation.proposed`, `remediation.approved`, `remediation.denied`,
  `remediation.executed`, `remediation.validation_failed`;
- `reclaim.requested`, `reclaim.started`, `reclaim.resource_deleted`,
  `reclaim.cleanup_failed`, `reclaim.completed`, `reclaim.residue_detected`.

StarGate classification must preserve the original immutable event and emit a
new classification event. It must never rewrite Launchpad history.

## Logging contract

All participating services must emit JSON logs with:

- timestamp, severity, service, component, environment, source version;
- event name/action, outcome, reason code, duration;
- correlation, causation, trace, aggregate, workshop/session/seat, tenant, and
  cluster references when applicable;
- retry number, idempotency key, queue/lease ID, target dependency, and receipt
  ID for delivery/lifecycle workers;
- sanitized error class and evidence reference rather than raw response bodies.

Logs must never contain instructor codes, API keys, bearer tokens, kubeconfigs,
passwords, participant email addresses, prompts, model responses, document
contents, cookie values, or unredacted external error payloads. Hashes are not
automatically anonymous; prompt/document hashes also require an approved need.

## Durable delivery design

1. Persist the lifecycle mutation and its event in one database transaction
   using an outbox record.
2. A fenced publisher reads undispatched outbox rows and sends an immutable
   envelope to the versioned StarGate endpoint or approved event bus.
3. StarGate deduplicates by `event_id`, validates `schema_version`, records an
   immutable receipt, and returns `receipt_id`, accepted schema version, and
   stored payload hash.
4. Launchpad records each attempt, receipt, latency, response class, and next
   retry time without blocking lifecycle completion.
5. Exponential backoff, bounded retries, circuit breaking, and a dead-letter
   state preserve failed events for operator replay.
6. Replay retains original `event_id`, `occurred_at`, sequence, and payload;
   delivery-attempt metadata changes separately.
7. Mutual trust uses approved TLS and scoped workload identity/API credentials;
   certificate verification cannot be disabled.

Delivery is at least once. Idempotency and aggregate sequence make duplicates
safe and expose gaps without requiring fragile exactly-once claims.

## Metrics and alerts

Use bounded labels such as `source`, `event_type`, `outcome`, `reason_code`,
`cluster`, `catalog_item`, and schema version. Required signals include:

- events created, delivered, retried, dead-lettered, rejected, and replayed;
- outbox depth and age of oldest undelivered event;
- delivery and receipt latency;
- schema-validation and sequence-gap counts;
- evidence coverage by lifecycle stage;
- incidents by failure class and catalog/cluster pair;
- proposed, approved, denied, executed, successful, and rolled-back remediation;
- reclaim duration and residue outcome.

Alert on an aging outbox, sustained delivery failure, rejected schema, sequence
gap, consumer lag, missing required lifecycle evidence, receipt hash mismatch,
and a cleanup failure lacking classification within its SLO.

## StarGate product-list contract

The Launchpad product/operations list should receive a bounded StarGate summary,
not scrape raw logs. The summary includes:

- product ID, display name, owner, version, support contact, and documentation;
- deployment/endpoint and trust state without credentials;
- current health, last successful receipt, consumer lag, and oldest queued event;
- supported schema versions and event classes;
- enabled capabilities: evidence, preflight, classification, recommendation,
  approved execution, automatic execution;
- maturity per capability: `planned`, `contract`, `integration`, `pilot`, or
  `production`;
- coverage: clusters, catalogs, lifecycle stages, and recent evidence ratio;
- active incident/failure-class summary and evidence-manifest links;
- explicit unavailable/degraded reason.

The list must not claim “healthy” solely because the StarGate Route returns
HTTP 200. Health requires producer outbox, delivery, consumer receipt, storage,
schema compatibility, and a recent synthetic event round trip.

## Security and retention decisions

Before implementation, security and product owners must approve:

- event and log data classification;
- hot/searchable/archive retention by signal class;
- tenant isolation and support-role access;
- encryption and workload identity;
- deletion/legal-hold behavior;
- geographic/data-residency constraints;
- audit access and incident-response procedures.

Evidence manifests retain hashes and references; they do not become an
unbounded copy of raw logs or participant data.

## Release gates

1. **RED contract:** tests demonstrate missing fields, incorrect
   `cleanup_failed` outcome, dropped delivery, duplicate delivery, ordering gap,
   incompatible schema, and sensitive-field rejection.
2. **GREEN component:** outbox, publisher, consumer, receipt, deduplication,
   replay, metrics, and product summary pass independently.
3. **GREEN integration:** deployed Launchpad and StarGate exchange all required
   lifecycle stages through restart and network-failure tests.
4. **GREEN pilot:** one 1-seat and one 5-seat workshop produce complete evidence
   and a truthful product-list status; StarGate outage does not stop Launchpad.
5. **GREEN scale:** the certified workshop burst produces no lost events,
   bounded lag, no high-cardinality metrics, and complete reclaim evidence.
6. **Autonomy gate:** each remediation class separately proves authorization,
   target ownership, idempotency, post-validation, circuit breaking, rollback,
   and audit before moving beyond recommendation.

## Backlog mapping

- `PILOT-BUG-011`: `cleanup_failed` has the wrong outcome classification.
- `PILOT-BUG-012`: StarGate lifecycle delivery is not durable or replayable.
- `PILOT-FEAT-008`: versioned StarGate telemetry, evidence, and product summary.
- Product roadmap: `LP-E017`, `LP-S021`, and `LP-S022`.
