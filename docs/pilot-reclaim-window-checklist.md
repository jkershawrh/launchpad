# September pilot reclaim window: operator checklist

This is a preparation checklist, **not approval or a reclaim command**. It
does not change a live workshop. The September 21 interim evidence counted
nine retained workshops and 270 seats across Arena, Brutus, and Flightpath;
those counts are a historical baseline, not tomorrow's inventory. The last
recorded Brutus API refusal prevents a whole-fleet readiness claim until its
recovery is independently observed.

## Before the window

1. Record the named event owner, approved retention end, exact workshop IDs,
   target clusters, start time, and go/no-go approver. Confirm that no trainer
   has requested continued access. Do not infer approval from an expired TTL.
2. At T-30 minutes or later, collect a **new** complete, read-only roster and
   namespace inventory on every persisted target. The local source is
   `PYTHONPATH=backend .venv/bin/python -m app.services.reclaim_live_source`.
   It emits only a checked complete JSON snapshot; a failure emits no partial
   inventory and blocks the operation. Preserve the raw output only in the
   approved private evidence location, not in Git or a chat.
3. Run `app.services.reclaim_readiness` against that fresh snapshot. Require
   matching full workshop/session IDs, all seat numbers, target clusters,
   namespace ownership, and reservations. Compare the exact retained-workshop
   set with the September pilot ledger; investigate additions, omissions, or
   changed states rather than silently narrowing the scope.
4. Independently inventory every workshop's entitlement and claim counts,
   Routes, RoleBindings, Argo CD Applications, PVCs, model keys, active jobs,
   audit cursor, and any orphan labels. The narrow balance checker does **not**
   certify these resources. Hash a sanitized evidence manifest; exclude
   passwords, instructor codes, tokens, model keys, and participant email.
5. Record cluster/API health and the participant-facing access state. If any
   target (including Brutus) cannot be authenticated and inventoried, mark the
   whole-fleet gate **blocked**. Do not redirect cleanup to another cluster.

## During the approved window

1. Reconfirm approval and the exact target IDs immediately before mutation.
   Start with one explicitly selected canary workshop; do not reclaim the other
   eight by implication.
2. Use Launchpad's workshop-scoped lifecycle reclaim on the workshop's
   persisted `cluster_ref`. Record start time, state transitions, retries,
   target, and audit events. Do not use ad hoc namespace deletion as a substitute
   for lifecycle cleanup.
3. Verify participant access is denied and all owned namespaces, Routes,
   RoleBindings, Argo CD Applications, PVCs, model keys, entitlements,
   reservations, and active jobs are gone. Confirm unrelated workshops remain
   healthy. Measure cleanup time against the ten-minute objective.
4. If the canary has residue, wrong-target activity, or participant access
   still succeeds, stop the remaining waves, retain evidence, and escalate.
   A reclaim cannot be rolled back by restoring an old UI status.
5. Only after canary acceptance, process the remaining approved workshops in
   bounded waves. Repeat the same receipt and residue checks per workshop and
   per cluster; never treat a successful API response alone as proof.

## Closeout

- Reconcile every seat to an explained terminal state and verify zero managed
  residue and zero orphan records across all three execution clusters.
- Publish duration, failures/retries, capacity release, audit linkage, and
  hashes of sanitized evidence. Keep raw operational evidence in its approved
  store and link only safe summaries from the roadmap.
- Mark LP-T071/072 complete only after the approved live run and independent
  verification. A local dry run or an unreachable cluster cannot count as
  GREEN-live.

## Candidate 02 convergence handoff

The reclaim closeout and the control-plane rollout are separate approvals.
Zero residue does not implicitly authorize a deployment. After all retained
workshops are closed, use this order for
`launchpad-staging-20260922-02`:

1. Freeze new orders and record the empty-system inventory, database migration
   level, active lifecycle jobs, current image digests, and current deployment
   replica counts.
2. Produce an encrypted Arena PostgreSQL backup with
   `scripts/launchpad-dr-database.sh backup`. Verify its checksum and record the
   artifact location in the private operator record. Do not put the artifact,
   recipient, identity, credentials, or database contents in Git evidence.
3. Record rollback ownership and the exact rollback trigger: readiness failure,
   migration failure, public authorization regression, lifecycle duplication,
   or any unexplained resource mutation. The previous image digests and
   configuration must remain available until acceptance finishes.
4. Re-run the repository candidate validator and the Arena overlay component
   tests from a clean checkout of revision
   `39517f527c03c646108c7dfe0e97487befdfdce3`. Require candidate ID `02`, three
   exact effective catalog releases, two backend replicas, leased lifecycle,
   suspended automation, and zero rendered Secret objects.
5. Apply only the guarded `arena-convergence-canary/apply.sh` entry point with
   an explicit Arena kubeconfig and its exact candidate confirmation. This is a
   deployment operation and needs a separate named go/no-go decision at the
   window; preparing or merging this checklist is not that approval.
6. Prove both backend replicas ready, one lifecycle owner per job, unchanged
   public URL and Keycloak issuer, successful requester/admin health, and no
   duplicate lifecycle mutation. Keep orphan deletion and new ordering off.
7. Run the deployed contract and integration suite. If it passes, record a new
   immutable evidence manifest and request named promotion from `green-local`
   to `green-integration`; never edit the existing receipt to imply the result.
8. Re-enable ordering only for three one-seat exact-release canaries—one per
   pilot catalog. Each must prove public claim, learn, execute, resume, restart,
   reclaim, authorization denial, and zero residue before `green-canary` can be
   requested.

Stop and roll back if the backup cannot be verified, the retained inventory is
not empty and explained, either backend replica is unavailable, more than one
worker owns a lifecycle job, the public issuer changes, or any canary leaves
residue. Candidate `01` remains historical evidence and must not be rewritten
or treated as a rollback deployment package.

Related contracts: [readiness](reclaim-readiness-local-contract.md),
[collector](reclaim-inventory-collector-local.md), and
[September 21 interim evidence](../evidence/runs/pilot-closeout/retained-evidence-validation-20260921.json).
