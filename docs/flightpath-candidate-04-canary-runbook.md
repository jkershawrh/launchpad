# Flightpath Candidate 04 canary promotion and certification

Candidate 04 is the first six-catalog Flightpath convergence candidate. Its
machine-readable promotion and rollback authority is
`certification/releases/flightpath-candidate-04/bundle.yaml`. This runbook does
not authorize a promotion while any retained workshop or session is active.

## Certified scope

The candidate binds the exact platform revision, three signed GHCR images, and
the following catalog revisions:

1. Intel AI 101: Serve LLMs on Intel Xeon
2. Intel AI 201: Build an AI Agent
3. Intel AI 201: Build Multi-Agent AI Systems
4. Intel AI 301: Engineer Reliable Agentic Workflows
5. Intel AI 301: Hybrid Fraud Detection
6. Intel AI 301: Build an Evidence-Backed Network Operations Agent

All six require a complete internal one-seat lifecycle. Although the pinned
Multi-Agent and Network Operations manifests both permit `public_code`, this
release gate authorizes the public claim journey for Network Operations only,
with a hard limit of one public seat. Multi-Agent public access remains outside
this canary plan. This does not certify the other five catalogs for public
access or any catalog for multi-seat scale.

## Stop conditions

Do not apply the promotion when any of these conditions is false:

- the release owner approved the exact bundle;
- `oc whoami --show-server` equals the API server in the bundle;
- the candidate database contains zero active workshops and zero active lab
  sessions;
- the requester, admin, and API hostnames all resolve to the active Flightpath
  ingress and return their expected authenticated response;
- no managed seat namespace or lifecycle mutation remains in flight;
- the current encrypted database backup and checksum have been independently
  verified;
- required Secrets already exist through the approved out-of-band process;
- the exact rendered manifest passes server-side dry-run;
- the reviewed server-side diff stays inside the candidate namespace and the
  explicitly declared cluster-scoped RBAC objects; and
- the rollback owner and decision deadline are recorded.

Historical failed/completed records do not by themselves block promotion, but
active `requested`, `provisioning`, `validating`, `ready`, `reclaiming`, or
`cleanup_failed` records do. Never change record state by hand to pass this
gate.

## Prepare immutable promotion and rollback payloads

Run from a clean checkout containing the pinned commits:

```sh
python3 scripts/validate_flightpath_promotion_bundle.py \
  certification/releases/flightpath-candidate-04/bundle.yaml
python3 scripts/validate_flightpath_promotion_bundle.py \
  certification/releases/flightpath-candidate-04/bundle.yaml \
  --render promotion --output /secure/release/flightpath-candidate-04.yaml
python3 scripts/validate_flightpath_promotion_bundle.py \
  certification/releases/flightpath-candidate-04/bundle.yaml \
  --render rollback --output /secure/release/flightpath-candidate-04-compatible-rollback.yaml
```

Retain the reported SHA-256 values with the two payloads. Never regenerate the
rollback from the current working tree.

## Preflight and backup

1. Select the explicit Flightpath kubeconfig; do not switch a shared context.
2. Capture current workloads, routes, PVCs, image identities, and cluster-scoped
   objects named by the candidate. Do not export Secret values.
3. Resolve the requester, admin, API, Console, OAuth, and router hostnames. Stop
   if an application hostname points at a different or unreachable ingress.
   A healthy in-cluster Service does not satisfy this browser-access gate.
4. Query the Launchpad API or database read-only and attach the zero-active-
   workshop/session result to the evidence run.
5. Produce and verify an encrypted candidate database backup using the
   procedure in `docs/flightpath-candidate-03-staging-runbook.md` with a new
   Candidate 04 filename and an externally supplied age recipient.
6. Run server-validated dry-run against the already rendered promotion payload:

   ```sh
   KUBECONFIG=/explicit/flightpath.kubeconfig \
     oc apply --dry-run=server \
     -f /secure/release/flightpath-candidate-04.yaml -o name
   ```

   Do not add `--server-side` or `--force-conflicts`. The existing candidate is
   owned by the client-side apply manager. Changing field ownership is a
   separate migration requiring its own diff, approval, and rollback proof.
7. Save and review the diff. Stop on unexpected namespace, image, Route, RBAC,
   storage, database, or Secret-reference changes.

## Promote the platform

Apply only the verified Candidate 04 payload. Observe in this order:

1. database migration and PostgreSQL readiness;
2. backend and lifecycle-worker readiness;
3. requester and admin readiness;
4. public gateway and named tunnel readiness;
5. exact deployed image digests;
6. requester, admin, API, and public-origin health probes; and
7. model inventory and authenticated inference health.

Stop new orders and roll back on migration failure, identity drift, cross-tenant
behavior, model authorization failure, or unexplained readiness failure.

## Six-catalog one-seat matrix

Run catalog canaries sequentially so one failure cannot be hidden by another.
For each catalog record order ID, session ID, namespace, cluster, catalog
version, source revision, image digests, timestamps, screenshots/probes, audit
events, and cleanup evidence.

Each internal canary must prove:

- capacity preview and order select Flightpath;
- exactly one seat is created and becomes ready;
- Showroom loads the pinned content;
- every declared tab and route works in the intended embedded experience;
- the terminal starts in the assigned namespace with namespace-scoped RBAC;
- the documented learner workflow completes against the required model;
- logout/resume preserves only the correct entitlement;
- manual reclaim and TTL expiry are idempotent; and
- the namespace, Routes, RoleBindings, Argo CD objects, model key, reservation,
  entitlement, and lifecycle records leave zero active residue.

For Network Operations, repeat the learner journey through
`https://labs.smg-helix.ai` using a newly generated one-time instructor code.
Also prove invalid-code denial, same-email seat recovery, logout/resume,
cross-seat denial, expiration denial, identity cleanup, and the one-public-seat
limit. Never record the plaintext instructor code in evidence or Git.

## Promotion decision

Advance Candidate 04 to `green-canary` only when every required matrix row is
green and its immutable evidence manifest is committed. Any failure first
becomes a regression test. A failed catalog remains failed even when the other
five pass.

This gate does not certify five-seat, 25-seat, or 30-seat operation. Those
profiles, fault injection, security negative tests, backup/restore, upgrade,
rollback, performance, and soak remain required for `green-staging`.

## Rollback

Stop new orders and application writers before applying the verified Candidate
04 compatibility rollback payload. The rollback preserves Candidate 04's
catalog, route, RBAC, and volume shape while reverting the backend, requester,
and admin runtime images to the previously working set. Do not apply the stale
Candidate 03 object shape. Application rollback does not authorize database restore.
A database restore requires a separately proven compatible backup, explicit
RPO/data-loss acceptance, and database-owner approval. After rollback, verify
the compatibility rollback image identities, platform health, closed order ingress, and
zero active lifecycle or workshop residue.
