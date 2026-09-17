# Launchpad VEF pilot lane

VEF is integrated as a read-only evidence lane. It does not run in participant
labs, alter lab content or links, change routing, deploy a proxy, query the
Launchpad database, or contact a cluster. Existing aggregate receipts remain
the operational evidence source; private cost and validation inputs are joined
outside the labs.

## Pilot boundary

The planned boundary is 90 provisioned seats for 75 enrolled users. These are
different measures. The scorecard must separately report provisioned seats,
enrolled users, observed active users, and successful journeys. An unused seat
is not a participant outcome.

Retained evidence currently supports 75 simultaneous participant journeys,
including three successful exact-75 functional runs and a clean 60-minute
soak. It does not certify 90 simultaneous active users. The current release
decision remains a conditional go for a supervised internal pilot.

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
`schemas/vef/launchpad-pilot-input.v1alpha1.schema.json`, then run:

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
and inference-cost evidence; measured marginal delivery cost; and manual,
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
