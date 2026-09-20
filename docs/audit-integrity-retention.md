# Audit integrity and retention

The authoritative policy is
[`contracts/audit-integrity-retention-v1.yaml`](../contracts/audit-integrity-retention-v1.yaml).
It defines the event envelope, actor/action/target/outcome correlation,
redaction boundary, retention classes, append-only integrity design, export
authorization, deletion receipts, and legal-hold behavior.

The current repository proves only that the contract is complete and fails
closed. It does **not** claim that the operational database is immutable, that
hash chains and external anchors are deployed, or that retention, exports,
legal holds, restore, and disposition have passed live certification. Those
items remain explicit release blockers.

Run the local check with:

```console
python3 scripts/validate_audit_integrity_retention.py
```

The validator rejects missing accountability fields, incomplete secret and PII
redaction, mutable producer permissions, missing retention ownership or
durations, incomplete export manifests, early deletion, weak legal holds,
dangling verification cases, and missing evidence files. Production requires
all declared verification cases, no unresolved critical or high risks, and an
independent security review.

## Operational design boundary

Events are immutable facts. A correction is a new event that references the
superseded event. Producers may append but cannot read, export, update, or
delete. Investigators can read and verify but cannot alter retention. Exports
require a separate approver, encryption, a content-hashed manifest, and their
own access event. Retention expiry cannot delete held records and must produce
a tamper-evident disposition receipt and tombstone.
