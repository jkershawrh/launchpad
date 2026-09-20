-- Durable, draft-only catalog intake submissions. This table has no foreign
-- key or trigger into the live catalog and cannot activate an orderable item.

CREATE TABLE IF NOT EXISTS catalog_intake_drafts (
    intake_id            TEXT PRIMARY KEY,
    request_fingerprint  TEXT NOT NULL,
    catalog_item_id      TEXT NOT NULL,
    repository_url       TEXT NOT NULL,
    revision             TEXT NOT NULL,
    state                TEXT NOT NULL CHECK (state = 'draft'),
    data                 JSONB NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (revision ~ '^[0-9a-f]{40}$')
);

CREATE INDEX IF NOT EXISTS idx_catalog_intake_drafts_catalog_revision
    ON catalog_intake_drafts (catalog_item_id, revision);
