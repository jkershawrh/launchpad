# Flightpath Candidate 03 staging promotion and rollback

This runbook packages Candidate 03 for a controlled internal staging promotion.
It does not authorize public traffic, modify Flightpath, or include Secret data.
The machine-readable identity is
`certification/releases/flightpath-candidate-03/bundle.yaml`.

## Stopping conditions

Stop before applying anything unless all of the following are true:

- the named release owner approves this exact bundle;
- Flightpath reports the exact API server recorded in the bundle;
- there are no retained workshops in the candidate namespace;
- a current database backup has been verified and its restore owner recorded;
- all required Secrets already exist through the approved out-of-band path;
- server-side dry-run accepts the exact rendered promotion manifest; and
- a rollback owner and decision deadline are recorded.

For this isolated candidate, create the encrypted backup from the candidate
namespace rather than the historical `partner-ai-launchpad` namespace:

```sh
LAUNCHPAD_NAMESPACE=launchpad-flightpath-candidate \
  scripts/launchpad-dr-database.sh backup \
  /explicit/flightpath.kubeconfig \
  /secure/backups/flightpath-candidate-03-TIMESTAMP.dump.age \
  AGE_RECIPIENT
scripts/launchpad-dr-database.sh verify \
  /secure/backups/flightpath-candidate-03-TIMESTAMP.dump.age \
  /secure/backups/flightpath-candidate-03-TIMESTAMP.dump.age.sha256
```

`AGE_RECIPIENT` and the durable encrypted destination are external security
inputs. Never invent a recipient, store an age identity in Git, or substitute
an unencrypted local dump.

Trusted public DNS/TLS remains blocked. Do not enable a public Route or use this
promotion as evidence of a public participant journey.

## Prepare deterministic artifacts (read-only)

Run from a clean checkout that contains both pinned commits. The validator
exports the selected commit, renders only its pinned overlay, and rejects any
payload whose SHA-256 differs from the bundle.

```sh
python scripts/validate_flightpath_promotion_bundle.py \
  certification/releases/flightpath-candidate-03/bundle.yaml
python scripts/validate_flightpath_promotion_bundle.py \
  certification/releases/flightpath-candidate-03/bundle.yaml \
  --render promotion --output /secure/release/flightpath-candidate-03.yaml
python scripts/validate_flightpath_promotion_bundle.py \
  certification/releases/flightpath-candidate-03/bundle.yaml \
  --render rollback --output /secure/release/flightpath-candidate-02-rollback.yaml
```

Record both output hashes and retain both files together. Never rebuild a
rollback payload from the current working tree.

## Operator preflight

1. Export `KUBECONFIG` to the explicitly selected Flightpath credential.
2. Confirm `oc whoami --show-server` exactly equals the bundle API server.
3. Confirm the active namespace is `launchpad-flightpath-candidate` and has no
   retained workshop, learner, order, or reclaim activity.
4. Capture current Deployments, StatefulSets, Jobs, ConfigMaps, Routes, PVCs,
   and image identities as rollback evidence. Do not export Secret values.
5. Verify the database backup and checksum independently. Candidate 02 is an
   application-manifest rollback only; it does not authorize database restore.
6. Run server-side dry-run with the already rendered promotion file and save
   its output for approval review.
7. Review the server-side diff. Any namespace, image, Route, RBAC, PVC, or
   Secret reference outside the approved scope stops the promotion.

## Promote

After the named approval, apply only the verified promotion file. Keep order
ingress and public traffic disabled. Observe database readiness first, then the
backend and lifecycle worker, then the internal portal and admin surfaces.
Do not advance when migration, readiness, model connectivity, catalog identity,
or reclaim checks fail.

Run the existing Flightpath certification checks and capture their immutable
output. The promotion is successful only when internal order, readiness, and
zero-residue reclaim pass against the exact Candidate 03 identities.

For the Candidate MaaS authorization correction, retain the deployed digest
and run the three-interval proof without printing the key:

```sh
scripts/certify_flightpath_maas_health.sh \
  /explicit/flightpath.kubeconfig \
  launchpad-flightpath-candidate \
  sha256:e922ef53a5e08ae957de8b0a034652f7d64d605e09bdc032a6405279ba9c16e1
```

Do not mark `PILOT-BUG-014` verified from a single direct request. The script
requires the exact deployed digest, three authenticated inventory requests,
three successful scheduled model-health intervals, and no authorization or
credential-bearing log output.

## Roll back

Trigger rollback on failed migration, failed readiness, catalog/image identity
drift, loss of model connectivity, cross-tenant behavior, or reclaim residue.
Immediately stop new orders and scale application writers down before applying
the verified Candidate 02 rollback file.

Do not restore a database merely because the application manifest was rolled
back. Database restore requires a separately verified compatible backup,
explicit data-loss/RPO acceptance, and approval from the database owner. If
compatibility is unknown, leave writers stopped and escalate instead of
guessing.

After application rollback, verify Candidate 02 image identities, readiness,
order ingress remains closed, no lifecycle lease is advancing unexpectedly,
and no workshop residue exists. Record the trigger, timestamps, operator,
payload hashes, database decision, and final state.
