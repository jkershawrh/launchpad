-- Provisioning outcomes: track success/failure per catalog×cluster×hardware
-- for the feedback loop intelligence layer.

CREATE TABLE IF NOT EXISTS provisioning_outcomes (
    outcome_id      TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    request_id      TEXT NOT NULL,
    catalog_item_id TEXT NOT NULL,
    cluster_name    TEXT,
    hardware_profile TEXT NOT NULL,
    data            JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outcomes_catalog ON provisioning_outcomes (catalog_item_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_cluster ON provisioning_outcomes (cluster_name);
CREATE INDEX IF NOT EXISTS idx_outcomes_hardware ON provisioning_outcomes (hardware_profile);
CREATE INDEX IF NOT EXISTS idx_outcomes_composite ON provisioning_outcomes (catalog_item_id, cluster_name, hardware_profile);

-- Orchestration decisions: audit trail for placement decisions.

CREATE TABLE IF NOT EXISTS orchestration_decisions (
    decision_id     TEXT PRIMARY KEY,
    request_id      TEXT NOT NULL,
    data            JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_request ON orchestration_decisions (request_id);
