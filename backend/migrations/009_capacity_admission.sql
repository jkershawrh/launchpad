-- Durable decisions and aggregate holds for the capacity-admission v1 contract.
-- The store serializes each cluster and idempotency key with PostgreSQL advisory
-- transaction locks before reading active holds and writing one whole-workshop result.

CREATE TABLE IF NOT EXISTS capacity_admission_decisions (
    decision_id          TEXT PRIMARY KEY,
    idempotency_key      TEXT NOT NULL UNIQUE,
    request_fingerprint  TEXT NOT NULL,
    workshop_id          TEXT NOT NULL UNIQUE,
    cluster_ref          TEXT NOT NULL,
    status               TEXT NOT NULL CHECK (status IN ('accepted', 'rejected')),
    decided_at           TIMESTAMPTZ NOT NULL,
    data                 JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS aggregate_capacity_reservations (
    reservation_id       TEXT PRIMARY KEY,
    decision_id          TEXT NOT NULL UNIQUE
                         REFERENCES capacity_admission_decisions(decision_id),
    idempotency_key      TEXT NOT NULL UNIQUE,
    workshop_id          TEXT NOT NULL,
    cluster_ref          TEXT NOT NULL,
    model_id             TEXT NOT NULL,
    model_release        TEXT NOT NULL,
    status               TEXT NOT NULL CHECK (status IN ('held', 'released')),
    created_at           TIMESTAMPTZ NOT NULL,
    released_at          TIMESTAMPTZ,
    cleanup_evidence_id  TEXT,
    data                 JSONB NOT NULL,
    UNIQUE (workshop_id),
    CHECK (
        (status = 'held' AND released_at IS NULL AND cleanup_evidence_id IS NULL)
        OR
        (status = 'released' AND released_at IS NOT NULL AND cleanup_evidence_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_aggregate_capacity_reservations_active_cluster
    ON aggregate_capacity_reservations (cluster_ref, model_id, model_release)
    WHERE status = 'held';
