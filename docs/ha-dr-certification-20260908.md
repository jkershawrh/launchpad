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
| HA-LEASE-01 | Only one worker owns an aggregate | GREEN | GREEN | — | GREEN (one seat) | GREEN-live-process |
| HA-FENCE-01 | Expired owner cannot heartbeat, checkpoint, complete, or continue | GREEN | GREEN | — | GREEN (one seat) | GREEN-live-process |
| HA-TAKEOVER-01 | A replacement worker receives a higher fencing token | GREEN | GREEN | — | GREEN (provision + reclaim) | GREEN-live-process |
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
| HA-DEPLOY-01 | Arena overlay selects two workers and disables legacy reconciliation | GREEN | — | GREEN | GREEN (same node) | GREEN-live-process |
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
| Provision/reclaim/TTL/reconcile integration | 20 | One-seat provision and reclaim takeover; 5/25-seat takeover and clean timing runs pending | 16 |
| Database availability and recoverability | 15 | Single PostgreSQL instance; restore drill pending | 0 |
| Arena worker and node availability | 10 | Two-worker overlay; second schedulable node pending | 0 |
| Operations UI, metrics, and alerts | 10 | Live lifecycle API plus local UI and rendered alerts | 8 |
| Flightpath restore, hard fence, and failback | 10 | Passive overlay and runbook only | 3 |
| **Total** | **100** | **Pilot enabled; not approved for production HA/DR** | **62** |

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

Both lifecycle processes currently run on `gnr2`; `rhgnr1` remains cordoned.
Therefore node HA remains RED. Five-seat and 25-seat workshop takeover, stable
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
5. Repeat the individual provision/reclaim takeover once without changing code
   or configuration and record clean takeover latency using the 30-second lease.
6. Stabilize and uncordon `rhgnr1`, force the owner node unavailable, and repeat
   the proof before calling the deployment node-HA.
7. Repeat at 5 seats and 25 seats. Record job IDs, fencing tokens, image digests,
   cluster state, timings, route probes, screenshots, and cleanup scans.

The deterministic one-seat repetition is implemented by
`scripts/certify-arena-lifecycle-process-ha.sh`. It requires an explicit Arena
kubeconfig and destructive-confirmation flag, refuses to run while `rhgnr1` is
uncordoned or the 30-second lease is absent, faults both provision and reclaim
owners, verifies higher fences and zero residue, and writes a credential-free
hashed evidence receipt. It does not alter the global kube context.

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
