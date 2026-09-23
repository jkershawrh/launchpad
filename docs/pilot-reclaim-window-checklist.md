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

Related contracts: [readiness](reclaim-readiness-local-contract.md),
[collector](reclaim-inventory-collector-local.md), and
[September 21 interim evidence](../evidence/runs/pilot-closeout/retained-evidence-validation-20260921.json).
