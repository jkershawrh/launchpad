-- Immutable, approved event demand and the certified-capacity decision made
-- before workshop reservation. Lifecycle resources are deliberately stored
-- elsewhere so creating this record cannot provision or reclaim a lab.

CREATE TABLE IF NOT EXISTS event_manifests (
    event_id   TEXT PRIMARY KEY,
    data       JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
