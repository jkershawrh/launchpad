# Local pre-reclaim readiness contract

This is a **repository-only, read-only** balance check for LP-T069/070 before
the separately approved LP-T071/072 lifecycle certification. It reads one
operator-supplied JSON file and prints a small result. It never queries a
cluster, creates a snapshot, submits reclaim, deletes resources, or changes
reservations. A `ready: true` result is **not authorization to reclaim**.

Run from the repository root:

```sh
PYTHONPATH=backend .venv/bin/python -m app.services.reclaim_readiness /path/to/inventory.json
```

The process exits `0` only for an internally balanced input and `2` for a
blocked input. Output has `ready`, `reason`, `workshops`, and `seats`; it does
not echo the inventory. The maximum input is 2 MB, 100 workshops, or 5,000
seats. The timestamp must be timezone-aware and no more than 30 minutes old.

## Input shape

This is a **normalized supplied-record contract**, not the raw Launchpad API
or Kubernetes schema. The inventory producer must project persisted records
and independently observed namespace ownership into this exact shape:

```json
{
  "schema_version": "reclaim-readiness/v1",
  "captured_at": "2026-09-21T12:00:00Z",
  "scope": {
    "workshop_ids": ["11111111-1111-4111-8111-111111111111"],
    "cluster_refs": ["arena"],
    "workshops_complete": true,
    "sessions_complete": true,
    "namespaces_complete": true,
    "reservations_complete": true
  },
  "workshops": [{
    "workshop_id": "11111111-1111-4111-8111-111111111111",
    "cluster_ref": "arena",
    "seat_count": 1,
    "reservation_id": "event-1:cohort-1:lab-1",
    "state": "ready"
  }],
  "sessions": [{
    "session_id": "22222222-2222-4222-8222-222222222222",
    "workshop_id": "11111111-1111-4111-8111-111111111111",
    "cluster_ref": "arena",
    "namespace": "launchpad-seat-1",
    "seat_number": 1,
    "state": "ready"
  }],
  "namespaces": [{
    "namespace": "launchpad-seat-1",
    "cluster_ref": "arena",
    "workshop_id": "11111111-1111-4111-8111-111111111111",
    "session_id": "22222222-2222-4222-8222-222222222222"
  }],
  "reservations": [{
    "reservation_id": "event-1:cohort-1:lab-1",
    "workshop_id": "11111111-1111-4111-8111-111111111111",
    "cluster_ref": "arena",
    "seat_count": 1,
    "state": "consumed"
  }]
}
```

Source mapping: `Workshop.workshop_id`, `num_users`, `cluster_ref`, and
`status` supply workshop fields; `Workshop.seats[*].seat_number` and its
`session_id` join to `LabSession.session_id`, `namespace`, `cluster_ref`, and
`status`. Namespace ownership must come from a read-only observation on that
**same persisted cluster**. `Workshop.metadata.event_reservation_id` joins to
`EventCapacityReservation.reservation_id`, `workshop_id`, `cluster_ref`,
`resources.seats`, and `status`. Event reservation IDs are opaque strings such
as `event:cohort:lab`, **not necessarily UUIDs**. Older workshops with no event
reservation use `null` and an empty `reservations` array. `ready` and `active`
are allowed retained workshop/session states. All workshop and session IDs must
be full canonical UUIDs; the short IDs in the September 17 inventory are not
adequate inputs.

The validator rejects absent or extra workshops, missing or duplicate seats,
non-contiguous seat numbering, missing or orphan namespace records,
cross-cluster/session/workshop ownership, absent or mismatched reservations,
unknown fields (including email or credential fields), stale input, and false
completeness declarations. Provisioned seats count whether claimed or not.

## Evidence and limits

The [September 17 inventory](active-seat-inventory-20260917.md) and the
[September 21 interim refresh](../evidence/runs/pilot-closeout/retained-workshops-20260921.json)
are historical and cannot be re-used as the fresh T-30 snapshot at an approved
post-expiry reclaim window. The older inventory's nine short workshop
IDs and summary counts are insufficient to construct this JSON. A trusted
read-only collector, scoped to the entire retained estate and every persisted
cluster, must supply full IDs and prove its four completeness declarations.
This validator can detect contradictions **inside that supplied file**; it
cannot prove that an omitted cluster, workshop, namespace, reservation, or
session was actually observed. Do not interpret self-reported `*_complete`
flags as independent evidence. The producer and independent inventory checks
remain a separate gate.

Do not include instructor codes, model keys, tokens, passwords, or participant
email addresses. Before an approved reclaim, also capture the broader T-30
snapshot in the inventory plan: entitlements, claims, Routes, Argo CD objects,
PVCs, RoleBindings, model keys, active jobs, audit cursor, and evidence hashes.
This narrow balance validator does not certify those resources, participant
access denial, zero residue, or the ten-minute cleanup objective. LP-T071/072
remain open until the approved canary and every later workshop complete their
observed lifecycle with no residue.
