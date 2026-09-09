# Lifecycle HA and Flightpath DR certification

This matrix is the release boundary for the durable provisioning and reclaim
iteration. `GREEN-local` proves code behavior, `GREEN-postgres` proves the
cross-process storage contract, `GREEN-render` proves the deployment shape,
and `GREEN-live` requires a controlled Arena or Flightpath exercise. A lower
stage never implies a higher one.

## Red/green matrix

| Evidence ID | Behavior | Unit/component | PostgreSQL | Manifest | Live | Status |
|---|---|---:|---:|---:|---:|---|
| HA-QUEUE-01 | Idempotent durable job creation | GREEN | GREEN | — | RED | GREEN-postgres |
| HA-LEASE-01 | Only one worker owns an aggregate | GREEN | GREEN | — | GREEN (clean one-seat rerun) | GREEN-live-process |
| HA-FENCE-01 | Expired owner cannot heartbeat, checkpoint, complete, or continue | GREEN | GREEN | — | GREEN (clean one-seat rerun) | GREEN-live-process |
| HA-TAKEOVER-01 | A replacement worker receives a higher fencing token | GREEN | GREEN | — | GREEN (clean provision + reclaim) | GREEN-live-process |
| HA-XNODE-01 | Node-separated workers take over provision and reclaim jobs across hosts | GREEN | GREEN | GREEN | GREEN (Arena) | GREEN-live-cross-node-process |
| HA-CANCEL-01 | Reclaim cancels provision and waits for aggregate ownership | GREEN | GREEN | — | RED | GREEN-postgres |
| HA-API-01 | Individual provision/reclaim returns a durable queued session | GREEN | — | — | GREEN (one seat) | GREEN-live-process |
| HA-API-02 | Workshop confirm, retry, direct create, and reclaim use the queue | GREEN | — | — | RED | GREEN-local |
| HA-READ-01 | API/admin reads observe state persisted by another worker | GREEN | — | — | RED | GREEN-local |
| HA-DB-FAIL-01 | Configured PostgreSQL read/write loss fails closed | GREEN | — | — | RED | GREEN-local |
| HA-TTL-01 | TTL work has one leased system owner | GREEN | GREEN | GREEN | RED | GREEN-render |
| HA-RECON-01 | Reconciliation mutations stop after ownership loss | GREEN | — | GREEN | RED | GREEN-render |
| HA-TARGET-01 | Provision and reclaim retain the persisted `cluster_ref` | GREEN | — | — | GREEN (Arena) | GREEN-live-process |
| HA-READY-01 | API readiness rejects standby, DB loss, or missing HA schema | GREEN | — | GREEN | GREEN (active/DB/schema) | GREEN-live-process |
| HA-OBS-01 | Admin reports jobs, leases, retries, failures, and takeovers | GREEN | — | GREEN | GREEN | GREEN-live-process |
| HA-ALERT-01 | Stalled jobs, reclaim, and failed jobs have Prometheus alerts | GREEN | — | GREEN | RED | GREEN-render |
| HA-DEPLOY-01 | Arena overlay selects two anti-affined workers and disables legacy reconciliation | GREEN | — | GREEN | GREEN (one per node) | GREEN-live-cross-node-process |
| DR-PASSIVE-01 | Flightpath renders with zero Deployments and suspended CronJobs | GREEN | — | GREEN | RED | GREEN-render |
| DR-FENCE-01 | Runbook requires a hard Arena credential/network fence | GREEN | — | GREEN | RED | GREEN-render |
| DR-IDENTITY-01 | Flightpath has a distinct least-privilege identity for Arena and Brutus | GREEN | — | GREEN | RED | GREEN-render |
| DR-PREFLIGHT-01 | Read-only promotion gate rejects missing Secrets, mutable/internal images, storage, or incorrect roles | GREEN | — | GREEN | RED | GREEN-local |
| DR-BACKUP-TOOL-01 | Backup tool encrypts and checksums data and requires explicit Flightpath restore confirmation | GREEN | — | GREEN | RED | GREEN-local |
| DR-SECRET-01 | Dedicated service accounts and encrypted secret restoration | — | — | RED | RED | RED-blocked |
| DR-DATA-01 | Verified PostgreSQL backup and restore meets RPO | — | — | RED | RED | RED-blocked |
| DR-FAILOVER-01 | In-flight provision and reclaim survive Arena loss | — | — | GREEN | RED | RED-live |
| DR-RTO-01 | Flightpath recovery meets the 15-minute target three times | — | — | GREEN | RED | RED-live |

## Release rubric

The feature is intentionally disabled in the base deployment. Activation
requires every item below; this is a binary 100-point gate, not an average.

| Area | Points | Current evidence | Awarded |
|---|---:|---|---:|
| Durable queue, idempotency, cancellation | 15 | Local and PostgreSQL contracts | 15 |
| Lease ownership and fencing | 20 | Local, PostgreSQL, and live one-seat provision/reclaim worker-kill proof | 20 |
| Provision/reclaim/TTL/reconcile integration | 20 | Clean one-seat provision and reclaim takeover; 5/25-seat takeover runs pending | 16 |
| Database availability and recoverability | 15 | Single PostgreSQL instance; restore drill pending | 0 |
| Arena worker and node availability | 10 | Two anti-affined workers and cross-node process takeover; hard node-loss test pending | 5 |
| Operations UI, metrics, and alerts | 10 | Live lifecycle API plus local UI and rendered alerts | 8 |
| Flightpath restore, hard fence, and failback | 10 | Passive overlay and runbook only | 3 |
| **Total** | **100** | **Pilot enabled; not approved for production HA/DR** | **67** |

## Arena live process-takeover result

The one-seat Arena exercise is `GREEN-live-process-ha` for provision and
reclaim. Deleting the owning worker increased the provision fencing token from
1 to 8 and the reclaim token from 9 to 17. The same persisted Arena target was
retained, provisioning produced exactly one namespace and a Showroom HTTP 200,
and reclaim left zero Namespace, Route, RoleBinding, or Argo CD Application
residue. The public certification lab was intentionally preserved.

The live exercise found and fixed four defects: lifecycle-worker model-network
access, explicit worker CA selection, idempotent replay of an already reclaimed
session, and clearing stale lifecycle errors after a successful retry. Each fix
has a regression test. The immutable receipt is
`evidence/runs/arena-lifecycle-process-ha-20260908.json`.

This is functional takeover proof, not clean latency evidence. The first run
included defect discovery, deployments, and repeated recovery; it also began
with the earlier 120-second lease. A fresh uninterrupted run using the current
30-second lease is required before publishing a failover-time objective.

The earlier clean process proof ran both lifecycle processes on `gnr2` while
`rhgnr1` was cordoned. The later cross-node proof supersedes that topology,
but it does not change the boundary of the earlier receipt.

## Arena clean process-takeover result

The deterministic rerun on commit `bfef4a4` and backend image digest
`sha256:492a9fdcc15ca945fcff643b2a7762098f31073bb902cfba3c8ecbcb26131209`
is `GREEN-live-clean-process-ha`. Provision ownership transferred in 29.670
seconds and the recovered lab reached Showroom HTTP 200 in 110.754 seconds.
Reclaim ownership transferred in 30.009 seconds and completed in 30.155
seconds. Provision and reclaim each completed on the second attempt with a
higher fencing token. Cleanup left zero Namespace, Route, RoleBinding, or Argo
CD Application residue, and the public certification lab remained active.

The clean rerun exposed one additional recovery defect before it passed:
interrupted provisioning requested deletion of its partial namespace and then
immediately tried to reuse the same deterministic name while OpenShift still
reported the namespace as `Terminating`. The recovery path now performs a
bounded wait for namespace deletion before reprovisioning; its RED/GREEN
regression test and the complete 1,328-test non-local suite passed. The signed
evidence receipt is
`evidence/runs/arena-lifecycle-process-ha-clean-20260909T003840Z.json`.

## Arena cross-node process-takeover result

Arena now runs two lifecycle workers with required hostname anti-affinity: one
on `rhgnr1` and one on `gnr2`. Commit `fa02f59` executed the deterministic
cross-node proof against the same immutable backend image. In both phases the
initial owner ran on `rhgnr1` and the replacement owner ran on `gnr2`.
Provision ownership transferred with fencing token 1 to 2 in 31.623 seconds,
and the recovered lab reached Showroom HTTP 200 in 102.328 seconds. Reclaim
ownership transferred with fencing token 3 to 4 in 36.034 seconds and finished
in 40.010 seconds.

Cleanup left zero Namespace, Route, RoleBinding, or Argo CD Application
residue; both nodes returned Ready and schedulable; worker placement returned
to one process per node; and the public certification lab remained active. The
hashed receipt is
`evidence/runs/arena-lifecycle-cross-node-process-ha-20260909T011040Z.json`.

This certifies cross-node process takeover, not hard node failure. The proof
cordoned the owning node without draining it and deleted only the owning
Launchpad worker pod. A power, kubelet, or network-loss exercise for an entire
worker remains RED and requires a separate maintenance window because it can
affect unrelated workloads. Five-seat and 25-seat workshop takeover, stable
public DNS/TLS, and Flightpath DR also remain RED.

## Flightpath live preflight status

Read-only credential discovery on September 8 found the dedicated Arena
kubeconfig but no dedicated Flightpath kubeconfig. The promotion preflight was
therefore not run against Flightpath. This is the expected fail-closed result:
the disclosed bootstrap credential was not used, copied, or retained. Live DR
preflight remains blocked until a distinct least-privilege Flightpath credential
is delivered through the approved secret path.

## Arena activation sequence

1. Stabilize and uncordon a second Arena worker or change the pilot explicitly
   to single-replica lifecycle processing. Do not label one-node placement HA.
2. Build and mirror immutable application images to a registry reachable by
   Arena and Flightpath.
3. Apply migration `005_lifecycle_jobs.sql` while the feature flag remains off;
   verify `/ready` and a database backup.
4. Apply `deploy/launchpad/overlays/arena-ha-pilot` in a controlled window.
5. The clean individual provision/reclaim process-takeover repetition is
   complete. Retain its receipt as the process-HA baseline for later runs.
6. `rhgnr1` is uncordoned and cross-node process takeover is complete. Run a
   controlled hard node-loss exercise before calling the deployment node-HA.
7. Repeat at 5 seats and 25 seats. Record job IDs, fencing tokens, image digests,
   cluster state, timings, route probes, screenshots, and cleanup scans.

The deterministic one-seat repetition is implemented by
`scripts/certify-arena-lifecycle-process-ha.sh`. It requires an explicit Arena
kubeconfig and destructive-confirmation flag. Its baseline mode requires
`rhgnr1` to remain cordoned; `--cross-node` instead requires two Ready,
anti-affined workers on distinct nodes. Both modes fault provision and reclaim
owners, verify higher fences and zero residue, and write a credential-free
hashed evidence receipt. Neither alters the global kube context.

## Flightpath certification sequence

1. Replace the disclosed bootstrap credential with dedicated least-privilege
   service-account credentials and rotate the bootstrap credential.
2. Validate the exact Flightpath storage class and mirrored image pull paths.
3. Establish encrypted PostgreSQL and secret backups, then perform a restore
   without starting any Flightpath writer.
4. Hard-fence Arena, promote Flightpath in the runbook order, and execute the
   in-flight provision/reclaim drill.
5. Fail back using the same fence-first process. Repeat three times before the
   RPO/RTO objectives or DR readiness are advertised.
