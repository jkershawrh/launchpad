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
| HA-LEASE-01 | Only one worker owns an aggregate | GREEN | GREEN | — | RED | GREEN-postgres |
| HA-FENCE-01 | Expired owner cannot heartbeat, checkpoint, complete, or continue | GREEN | GREEN | — | RED | GREEN-postgres |
| HA-TAKEOVER-01 | A replacement worker receives a higher fencing token | GREEN | GREEN | — | RED | GREEN-postgres |
| HA-CANCEL-01 | Reclaim cancels provision and waits for aggregate ownership | GREEN | GREEN | — | RED | GREEN-postgres |
| HA-API-01 | Individual provision/reclaim returns a durable queued session | GREEN | — | — | RED | GREEN-local |
| HA-API-02 | Workshop confirm, retry, direct create, and reclaim use the queue | GREEN | — | — | RED | GREEN-local |
| HA-READ-01 | API/admin reads observe state persisted by another worker | GREEN | — | — | RED | GREEN-local |
| HA-DB-FAIL-01 | Configured PostgreSQL read/write loss fails closed | GREEN | — | — | RED | GREEN-local |
| HA-TTL-01 | TTL work has one leased system owner | GREEN | GREEN | GREEN | RED | GREEN-render |
| HA-RECON-01 | Reconciliation mutations stop after ownership loss | GREEN | — | GREEN | RED | GREEN-render |
| HA-TARGET-01 | Provision and reclaim retain the persisted `cluster_ref` | GREEN | — | — | RED | GREEN-local |
| HA-READY-01 | API readiness rejects standby, DB loss, or missing HA schema | GREEN | — | GREEN | RED | GREEN-render |
| HA-OBS-01 | Admin reports jobs, leases, retries, failures, and takeovers | GREEN | — | GREEN | RED | GREEN-render |
| HA-ALERT-01 | Stalled jobs, reclaim, and failed jobs have Prometheus alerts | GREEN | — | GREEN | RED | GREEN-render |
| HA-DEPLOY-01 | Arena overlay selects two workers and disables legacy reconciliation | GREEN | — | GREEN | RED | GREEN-render |
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
| Lease ownership and fencing | 20 | Local and PostgreSQL contracts; live kill test pending | 12 |
| Provision/reclaim/TTL/reconcile integration | 20 | Local and rendered; live workload pending | 12 |
| Database availability and recoverability | 15 | Single PostgreSQL instance; restore drill pending | 0 |
| Arena worker and node availability | 10 | Two-worker overlay; second schedulable node pending | 0 |
| Operations UI, metrics, and alerts | 10 | Local UI/API and rendered alerts | 7 |
| Flightpath restore, hard fence, and failback | 10 | Passive overlay and runbook only | 3 |
| **Total** | **100** | **Not approved for activation** | **49** |

## Arena activation sequence

1. Stabilize and uncordon a second Arena worker or change the pilot explicitly
   to single-replica lifecycle processing. Do not label one-node placement HA.
2. Build and mirror immutable application images to a registry reachable by
   Arena and Flightpath.
3. Apply migration `005_lifecycle_jobs.sql` while the feature flag remains off;
   verify `/ready` and a database backup.
4. Apply `deploy/launchpad/overlays/arena-ha-pilot` in a controlled window.
5. Run one individual provision while deleting its lifecycle-worker pod. Prove
   one namespace, one session, an increased fence, and a ready participant URL.
6. Run one reclaim while deleting its worker pod. Prove successful takeover and
   zero namespace, Route, RoleBinding, Application, model-key, or access residue.
7. Repeat at 5 seats and 25 seats. Record job IDs, fencing tokens, image digests,
   cluster state, timings, route probes, screenshots, and cleanup scans.

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
