# Capacity graduation plan: three concurrent 75-seat workshops

## Target

The target is **three concurrently active workshops with 75 isolated seats each**: 225 Showroom seats in total. This is a graduation target, not the current supported envelope. The current admission limit remains 25 seats per workshop until each gate below passes.

## Measured baseline — 2026-08-25

Oberon currently reports one schedulable node with:

- 255.5 CPU cores allocatable
- approximately 502 GiB memory allocatable
- 500 pods allocatable
- 149.6 CPU cores already requested (58%)
- approximately 309 GiB memory already requested (61%)
- 387 running pods

The original Showroom chart requests approximately 1.015 CPU and 848 MiB memory per seat and creates one pod plus one 5 GiB PVC. At that profile, 225 seats would request about 228 CPU, 186 GiB memory, 225 pods, and 1.1 TiB persistent storage. It cannot fit on the measured cluster.

The operator workshop now removes the demo frontend, shared inference gateway dependency, and per-seat terminal PVC. Its Showroom overrides request approximately 165 millicores and 464 MiB per seat. At that profile, 225 seats add approximately 37.1 CPU cores, 102 GiB memory, and 225 pods.

CPU becomes feasible after cleanup, but the current 500-pod ceiling is a hard blocker: 387 existing + 225 workshop pods exceeds it. Memory would also run above a safe operational threshold.

## Promotion gates

### Gate 0 — functional correctness

- Provision one `openshift-operators-workshop` seat.
- Verify the generated namespace contains Showroom but no `demo-frontend` deployment and no per-seat PVC.
- Verify Instructions, Terminal, and OpenShift Console tabs.
- Complete the Antora exercises and reclaim with zero residue.

### Gate 1 — small cohort

- Run 5 seats, then 10 seats.
- Record provisioning p50/p95, Argo sync time, route-ready time, pod startup, API throttling, and teardown time.
- Require 100% collective readiness and zero orphaned Applications, namespaces, Routes, and PVCs.

### Gate 2 — current supported ceiling

- Run 25 seats three times, including one cancel-during-provision test.
- Hold all seats active for at least 60 minutes.
- Require node requested CPU and memory below 75%, pod consumption below 70%, and no route instability.

### Gate 3 — one 75-seat workshop

- Add a separate operator-only limit flag and raise it from 25 to 75 only after Gate 2.
- Test 40, 50, then 75 seats; do not jump directly from 25 to 75.
- Start with provisioning concurrency 5 and tune only from measured API and Argo latency.
- Require at least 30% pod, CPU, and memory headroom after all 75 seats are ready.

### Gate 4 — concurrent workshops

- Run 2 × 75 with staggered starts, then simultaneous starts.
- Run 3 × 75 only after the two-workshop soak passes twice.
- Validate workshop-level admission so one order cannot consume capacity reserved for another.

## Infrastructure required for 3 × 75

Before Gate 4, provide one of these:

1. Add worker capacity and raise aggregate pod capacity to at least 850 pods, with at least 700 GiB allocatable memory; or
2. Place workshops across multiple OpenShift clusters using a capacity-aware placement adapter.

Multi-cluster placement is preferred for failure isolation. Each 75-seat workshop should be independently placeable and reclaimable, with no cluster context switching in operator procedures.

## Admission and observability work

- Make limits catalog/profile-specific: 25 general seats initially, then 75 only for the lightweight operator workshop.
- Account for existing requested resources and pod slots, not only static per-seat estimates.
- Reserve capacity atomically when an order is confirmed to prevent three simultaneous previews from overcommitting the same headroom.
- Publish live projected and actual CPU, memory, pod, PVC, namespace, Route, and Argo Application counts in the admin dashboard.
- Add alerts for route-ready p95, failed collective stability, API throttling, pending pods, and incomplete reclaim.

## Exit criteria

Three 75-seat workshops are production-supported only after two consecutive full tests meet all of the following:

- 225/225 seats collectively ready
- no Pending or repeatedly restarting Showroom pods
- p95 provision time within the published workshop SLO
- at least 30% infrastructure headroom at steady state
- complete group reclaim with zero namespace/Application/PVC residue
- a repeated run produces the same result without manual intervention
