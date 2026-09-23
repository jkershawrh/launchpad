# Launchpad VEF pilot lane

VEF is integrated as a read-only evidence lane. It does not run in participant
labs, alter lab content or links, change routing, deploy a proxy, query the
Launchpad database, or contact a cluster. Existing aggregate receipts remain
the operational evidence source; private cost and validation inputs are joined
outside the labs.

VEF is Launchpad's analytics, cost-allocation, and value-evidence layer. It is
not the operational observability system and does not replace cluster alerts.
Operational systems produce receipts; VEF reconciles their sanitized aggregates
into track outcomes, lifecycle performance, allocated cost, and gated value
claims.

The first aggregation boundary is defined by
`contracts/vef-aggregate-receipt-v1.yaml`. It accepts only four bounded receipt
types: track outcomes, platform lifecycle, AI usage, and cost allocation. It
rejects participant content and identity fields, duplicate receipts, mixed
pilot identities, unreconciled outcomes, and authoritative measurements that
contain unknown values. Its output fits the `v1alpha2` analytics and AI-usage
members, but it does not yet provide durable storage, replay, authenticated
lineage, or finance approval.

The contract is versioned. Existing `v1alpha1` inputs continue to produce the
original `v1alpha1` claim byte shape, without an analytics member. The analytics
and allocation extension is `v1alpha2`; it requires the new analytics section
and emits a `v1alpha2` claim. Consumers can therefore adopt the richer contract
without silently changing legacy reports.

## Pilot boundary

The planned boundary is 90 provisioned seats for 75 enrolled users. These are
different measures. The scorecard must separately report provisioned seats,
enrolled users, observed active users, and successful journeys. An unused seat
is not a participant outcome.

Retained evidence currently supports 75 simultaneous participant journeys,
including three successful exact-75 functional runs and a clean 60-minute
soak. It does not certify 90 simultaneous active users. The current release
decision remains a conditional go for a supervised internal pilot.

## Successful participant paths

Success is counted per enrolled participant, not per provisioned seat. A
participant succeeds only when one assigned seat becomes ready and the
preregistered contract for that participant's track completes within the
bounded pilot window. An unused seat, an HTTP response alone, or a partially
completed track is not a successful journey. Missing outcomes remain unknown.

The existing certification behavior defines the three paths:

- **Building an AI Agent:** the tools, agent, and application routes are
  healthy; the expected tool contract is present; the agent produces the
  required sourced architecture response without inference errors; the
  participant can edit only their own project and cannot read another project
  or list cluster nodes.
- **Multi-Agent Quickstart:** the participant UI and Showroom are reachable;
  research, analyst, and executor are ready and each completes an MCP-backed
  step without error; the participant UI workflow succeeds; the bounded
  learner policy works and rolls back; guardrail, semantic-routing, and
  authorization checks pass.
- **Serve LLMs:** the participant route is ready; authentication, workspace
  creation, and document ingestion succeed; the model answers with the planted
  fact and cites the supplied document; no application error is present.

An overall pilot success additionally requires complete participant
accounting, all preregistered safety thresholds, no isolation failure, no
cleanup residue, and completion of the manual requester/participant/admin
browser walkthrough. Report each track separately before reporting an overall
rate so one strong track cannot hide another track's failures.

Every track row declares its evidence state as `unavailable`, `partial`, or
`authoritative`. Track provisioned seats, successful journeys, failures, and
unknown outcomes must reconcile to the pilot-wide population and safety totals.
An activated journey must end as successful, failed, or explicitly unknown;
missing observations are never converted to zero.

### Launchpad platform path

Launchpad itself has a separate end-to-end outcome. A platform journey is
successful only when all of these stages pass:

1. **Request and approval:** an authorized requester submits the intended
   workshop/order and its catalog and entitlement contracts validate.
2. **Placement:** Launchpad selects only an approved cluster with capacity,
   persists the assignment, and does not split a workshop unexpectedly.
3. **Provisioning:** the expected seat records become ready within the
   preregistered SLO, without duplicate lifecycle ownership or an unexplained
   retry.
4. **Participant access:** an enrolled participant can claim only their
   assigned seat and reach the correct Showroom and lab while unauthorized
   cross-seat and cluster access remains denied.
5. **Operation and support:** health, successful/failed/unknown journeys,
   latency, and human interventions are captured as aggregate evidence without
   prompts, responses, identities, credentials, namespaces, or cluster details
   in the VEF export.
6. **Reclaim:** participant access is revoked and all Launchpad-owned lab
   resources are removed within the cleanup SLO with zero residue.

A ready lab alone is therefore not a successful Launchpad outcome. Report both
`lab_journey_success` and `launchpad_lifecycle_success`; this distinguishes a
working exercise from a platform that delivered and retired it reliably.

The lifecycle analytics contract also records orders requested, seats requested,
ready and reclaimed, provisioning and reclaim p95, human interventions, and
residue. Lifecycle analytics are decision-grade only when this evidence is
authoritative and residue is zero.

## Cost allocation and chargeback readiness

VEF separates observed cost from allocation policy. The sanitized allocation
ledger records shared platform cost, delivery/support cost, allocated inference
cost, unallocated cost, and the approved allocation basis. Supported bases are
seat-hour, successful journey, workshop, and direct metering.

`chargeback_ready` is false unless track and lifecycle analytics are ready, all
cost amounts are authoritative, no cost remains unallocated, a cost-center
mapping exists, and finance has approved the chargeback policy. This is a
readiness statement, not an invoice. Showback may display partial or unapproved
figures only when their evidence state and gaps remain visible.

The exporter derives total allocated cost and cost per successful journey. It
does not invent infrastructure prices, infer token cost from seats, spread an
unknown remainder across participants, or store employee-, participant-,
namespace-, or cluster-level allocation records.

## What the combined data can support

Operational data can state the number and rate of seats provisioned, enrolled
users, observed active users, successful journeys by track, unknown and failed
outcomes, journey latency, support interventions, platform health, isolation
checks, and cleanup completeness. With an independent matched baseline and a
complete cost ledger, it can also state observed cost per successful journey,
the difference from the current/manual process, attributable value, realization
cost, net value, time to value, and marginal cost per additional participant.

It cannot by itself state customer ROI, causal savings, 90-user concurrency,
or exact inference cost. Those conclusions require customer/finance validation,
the independent counterfactual, and authoritative request/token/pricing data.
The current 75-user evidence is capacity and operational proof, not a claim
that every provisioned seat or every successful technical check created value.

## Before the pilot

1. Copy `examples/vef-launchpad-pilot-intake.yaml` to an approved private
   planning location and resolve every `unknown`.
2. Preregister the successful-journey definition, bounded window, safety and
   cleanup thresholds, minimum meaningful improvement, and stop rules.
3. Record an independent matched baseline for the current/manual workshop
   preparation and support process. Rehearsal history may be used only as a
   clearly labeled directional baseline.
4. Use role-level loaded rates. Record engineering, facilitator, support,
   infrastructure, and other realization costs without employee-level records.
5. Complete the already-required manual frontend acceptance and dependency
   security triage. VEF does not weaken those release gates.

## During and after the pilot

Keep operational receipts in the existing evidence flow. Put private financial
inputs in `.vef-private/`; it is ignored. Create a sanitized input matching
`schemas/vef/launchpad-pilot-input.v1alpha2.schema.json`, then run:

```bash
python3 scripts/vef_export_pilot.py \
  --input .vef-private/pilot-input.json \
  --output vef-output/pilot-claim.json
```

Both locations are ignored. The exporter reads only the named input and emits
a deterministic candidate claim. It rejects common raw or identifying fields.

## Fail-closed rules

Claimable gross value remains zero unless all gates pass: an independent and
matched business baseline; complete participant accounting; no unknown
outcomes; no safety breach or cleanup residue; authoritative AI request, token,
and inference-cost evidence; authoritative track, lifecycle, and cost-allocation
evidence; zero unallocated cost; measured marginal delivery cost; and manual,
security, customer, finance, and privacy validation.

Launchpad currently exposes AI usage as unavailable because participant model
traffic uses direct endpoints. VEF preserves that unknown. Do not estimate
tokens from seat counts or modify lab traffic merely to improve the scorecard.

Technical readiness is not proof of ROI. Negative economic results and failed
gates are valid pilot outcomes and remain visible.

## No-effect verification

The VEF change is limited to `.vef/`, schemas, documentation, a standalone
exporter, tests, and report-only CI. Before and after integration, run the
existing repository tests and existing lab evidence contract tests unchanged.
No lab content, catalog item, site configuration, deployment manifest, Route,
or code link is part of this change.
