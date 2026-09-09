# Launchpad presenter demo walkthrough

## Audience and outcome

This is a 20-minute pilot walkthrough for Intel, Red Hat, and platform
stakeholders. It demonstrates one entry point, a whole-workshop placement,
participant isolation, a guided learner experience, operational visibility,
and deterministic reclamation. It does not present temporary public tunnels,
Oberon, Flightpath, or autonomous remediation as production-ready.

## Presenter setup

Complete these checks at least 30 minutes before the session:

1. Connect to the required internal network/VPN.
2. Confirm the requester portal, admin dashboard, backend `/health`, and target
   cluster Console are reachable.
3. Use the admin preflight to verify Arena and Brutus health and the selected
   catalog's capacity. Do not enable an uncertified cluster to make a preview pass.
4. Confirm all catalog sources and images are immutable and available.
5. Reclaim old pilot orders through Launchpad and verify no matching namespaces
   or Argo CD Applications remain.
6. Open the requester portal, admin operations page, and one prepared evidence
   report in separate tabs. Do not leave tokens, kubeconfigs, or Secrets visible.
7. Keep a pre-certified ready seat available as a fallback, but identify it as
   recorded evidence if a live dependency fails.

## Storyboard

| Time | Screen | Presenter action | Proof statement |
|---:|---|---|---|
| 0:00 | Title | State the problem: repeatable distributed labs without hand-building 75 environments | Git defines the experience; Launchpad owns its lifecycle |
| 1:30 | Catalog | Open the three event catalog items and point out category, required capabilities, and measured seat ceiling | A catalog is deployable content plus an executable proof contract |
| 3:00 | Request Environment | Select multi-seat workshop and one catalog; enter 25 seats | One order creates isolated seats; no manual workshop name is required |
| 4:00 | Capacity preview | Show selected cluster, complete-order fit, reservation, and ineligibility reasons | Launchpad rejects before seat creation if the whole order cannot fit |
| 5:30 | Confirm order | Submit and open the workshop view | `cluster_ref` is persisted before resource creation |
| 7:00 | Admin operations | Show grouped workshop/seat progress and cluster utilization | Operators see order, seat, cluster, latency, and failure context together |
| 9:00 | Participant seat | Open one ready seat and select **Open Lab** | Showroom, terminal, and operator experience belong to the assigned seat |
| 10:30 | Showroom | Follow one learner step; run the documented namespace-scoped command | Content is versioned and the participant works only in the assigned namespace |
| 13:00 | Application | Exercise the catalog-specific workflow and verify a real result | Pod readiness alone is insufficient; participant behavior is certified |
| 15:00 | Architecture | Explain Arena control plane, Arena/Brutus execution, and one-workshop affinity | Users enter once; placement details do not change the order model |
| 17:00 | Reclaim | Reclaim the workshop once from the owner/admin surface | Reclaim is group-scoped, idempotent, and targets the persisted cluster |
| 18:30 | Evidence | Show zero-residue result and certification matrix | Every claim links to a versioned contract and immutable evidence |

## Live learner checks

Use the catalog's own Showroom instructions and proof contract. At minimum,
demonstrate:

- the learner sees the correct catalog title and pages;
- the terminal opens in the seat namespace;
- `oc project` reports the assigned namespace;
- the participant can create an allowed namespaced resource;
- cross-namespace and cluster-scoped operations are denied;
- the application/agent/model journey returns its expected structural result;
- Console/operator links resolve to the selected execution cluster;
- the participant does not see another seat's resources.

Never substitute an administrator terminal for participant proof.

## Scale narrative

Say precisely:

> We staggered three 25-seat orders, ran all 75 participant environments at the
> same time across Arena and Brutus, completed the catalog-specific journeys,
> and reclaimed the run with zero remaining namespaces or Applications.

Do not say that Launchpad is GA, that any arbitrary 75-seat workshop fits one
cluster, that public access is stable, or that remediation is autonomous.

## Auto-remediation roadmap talk track

DeepField supplies fleet and inference signals. StarGate turns lifecycle and
signal evidence into a normalized failure class. A future GCL or GeoLux adapter
can propose a governed decision. Launchpad remains the only component allowed
to mutate the lab lifecycle and initially requires operator approval. Each
low-risk action advances from observe to recommend to approve to automatic only
after repeatable fault-injection proof.

## Recovery during the demo

| Symptom | Presenter response |
|---|---|
| Capacity preview unavailable | Show the ineligibility reason; do not bypass admission; move to recorded evidence |
| Seat remains provisioning | Show per-seat progress and bounded retry; use the prepared seat for learner flow |
| Showroom route fails | Verify correct cluster and Route; do not paste an internal URL into the participant page |
| Model call is warming | Explain inference-aware readiness and use the bounded documented retry |
| Console auth fails | Continue through the namespace-scoped terminal; record the Console gate as RED |
| Reclaim is slow | Show lifecycle job state; wait for verified cleanup rather than deleting the namespace directly |

## Close

End with three statements:

1. The internal pilot proves distributed 3 x 25 workshop lifecycle and use.
2. The next release gates are manual visual acceptance, stable public ingress,
   per-seat inference attribution, and HA/DR drills.
3. New labs enter through a repeatable Git discovery, intake, build, 1/5/25
   certification, promotion, support, and reclaim pipeline.
