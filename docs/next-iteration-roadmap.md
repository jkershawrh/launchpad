# Next-iteration pathways and roadmap

This document parks improvements that are valuable after the current visual
Showroom-scale release gate. They are not blockers for completing the present
25-seat participant-experience certification unless explicitly stated.

## Immediate release gate

Visually certify one complete 25-seat operator workshop. Follow the matrix in
`docs/oberon-workshop-readiness.md`, including representative browser journeys,
terminal exercises, cluster Console/Topology, cross-seat isolation, and clean
bulk reclaim.

Arena needs a browser-trusted wildcard certificate before it can satisfy this
gate. The certificate and private key are infrastructure inputs and must be
installed as Arena's default ingress certificate by a cluster administrator.

## Pathway 1: provisioning performance

- Replace in-request workshop execution with a durable queue and bounded workers.
- Permit organizers to submit multiple orders while execution is safely staggered.
- Measure per-cluster seat, Argo sync, route-ready, and collective-ready latency.
- Tune Argo and worker concurrency from observed saturation rather than static limits.
- Preserve whole-workshop cluster affinity and fail-closed capacity reservations.

Measured baseline for 25 seats on 2026-08-26:

- Oberon: approximately 14 minutes 9 seconds
- Arena: approximately 2 minutes 35 seconds to 2 minutes 54 seconds

## Pathway 2: organizer readiness estimates

- Show predicted readiness time during capacity preview and order confirmation.
- Display queued, provisioning, validating, and collectively-ready timestamps.
- Calculate estimates from recent cluster/catalog percentiles rather than constants.
- Show confidence and ineligibility reasons in the portal and admin dashboard.
- Publish an organizer-facing workshop startup SLO only after repeated runs.

## Pathway 3: automated participant experience

- Add a namespace-scoped validation runner that uses the same permissions as the
  Showroom terminal without granting the central provisioner token-mint or exec rights.
- Validate every generated Antora page and personalized attribute.
- Run the documented workload exercise and require an HTTP 200 response/body.
- Capture browser screenshots and console errors for representative seats.
- Keep human visual review as the final release check for layout and usability.

## Pathway 4: scale graduation

- Repeat 25-seat visual certification three times.
- Certify 50 seats on Arena only after retained capacity headroom is measured.
- Certify 75 seats on Arena only after the 50-seat gate passes.
- Continue toward the fleet goals in `docs/three-by-seventy-five-capacity-plan.md`.
- Do not advertise a seat limit inferred only from allocatable cluster capacity.
