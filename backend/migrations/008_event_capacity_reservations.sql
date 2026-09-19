-- Durable, aggregate event-capacity holds. The service acquires sorted
-- per-cluster PostgreSQL advisory transaction locks before it reads active
-- rows and inserts an entire EventReservationPlan in one transaction.

CREATE TABLE IF NOT EXISTS event_capacity_reservations (
    reservation_id   TEXT PRIMARY KEY,
    event_id          TEXT NOT NULL REFERENCES event_manifests(event_id),
    cohort_id         TEXT NOT NULL,
    lab_ref           TEXT NOT NULL,
    catalog_id        TEXT NOT NULL,
    catalog_release   TEXT NOT NULL,
    cluster_ref       TEXT NOT NULL,
    matrix_id         TEXT NOT NULL,
    matrix_digest     TEXT NOT NULL,
    fleet_snapshot_id TEXT NOT NULL,
    seats             INTEGER NOT NULL CHECK (seats > 0),
    cpu_millicores    BIGINT NOT NULL CHECK (cpu_millicores >= 0),
    memory_mib        BIGINT NOT NULL CHECK (memory_mib >= 0),
    pods              INTEGER NOT NULL CHECK (pods >= 0),
    storage_gib       BIGINT NOT NULL CHECK (storage_gib >= 0),
    routes            INTEGER NOT NULL CHECK (routes >= 0),
    model_slots       INTEGER NOT NULL CHECK (model_slots >= 0),
    status            TEXT NOT NULL DEFAULT 'held'
                      CHECK (status IN ('held', 'released', 'expired')),
    expires_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    released_at       TIMESTAMPTZ,
    data              JSONB NOT NULL,
    UNIQUE (event_id, cohort_id, lab_ref)
);

CREATE INDEX IF NOT EXISTS idx_event_capacity_reservations_active_cluster
    ON event_capacity_reservations (cluster_ref, expires_at)
    WHERE status = 'held';

CREATE INDEX IF NOT EXISTS idx_event_capacity_reservations_event
    ON event_capacity_reservations (event_id);
