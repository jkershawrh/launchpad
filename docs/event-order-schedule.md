# Event order schedule: local contract

`contracts/event-order-schedule-v1.yaml` defines a proposed, serial ordering
window for every cohort × lab workshop in an approved event manifest. It is a
pre-execution planning gate, not a scheduler or a live reservation.

The validator requires the schedule's event ID and SHA-256 digest of the full
canonical manifest to match, exactly one window per cohort/lab pair, both
manifest approvers, an approval time before ordering, timezone-aware positive
windows, no overlap between order windows, and each window to close by its
cohort start. The manifest must also have matching approved seat-environment
and retention counts. A changed catalog release, cohort size, lab assignment,
retention policy, or approver changes the digest and requires a new schedule.

Run the local gate with:

```bash
python scripts/validate_event_order_schedule.py \
  --manifest /path/to/event.yaml \
  --schedule /path/to/order-schedule.yaml \
  --output /path/to/order-decision.json
```

The command returns a machine-readable `GREEN-local` or `RED` decision and a
nonzero exit code on rejection. Compute `manifest_digest` with
`manifest_scope_digest(EventManifest.model_validate(manifest))`; the digest is
not a signature or proof that the named humans approved the plan.

This gate does **not** order workshops, reserve capacity, authorize public
access, or touch active labs. The current event API and reservation path do not
yet consume this schedule. Integration will require authenticated approval,
durable persistence, window enforcement by the lifecycle worker, fresh
capacity/model checks at dispatch, retry behavior when a window closes, and
operator visibility. Ordering windows do not establish a lower participant
concurrency bound or permit reuse of retained seats. Those claims require
enforceable access end times, successful cleanup evidence, and a separately
certified capacity policy.
