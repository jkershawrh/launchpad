-- Initial Launchpad schema: tenants, lab_requests, lab_sessions,
-- provisioning_plans, showback_records, catalog_items_custom.

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lab_requests (
    request_id      TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    catalog_item_id TEXT NOT NULL,
    status          TEXT NOT NULL,
    data            JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lab_requests_tenant_id ON lab_requests (tenant_id);
CREATE INDEX IF NOT EXISTS idx_lab_requests_status ON lab_requests (status);

CREATE TABLE IF NOT EXISTS lab_sessions (
    session_id      TEXT PRIMARY KEY,
    request_id      TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    catalog_item_id TEXT NOT NULL,
    status          TEXT NOT NULL,
    namespace       TEXT,
    data            JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lab_sessions_tenant_id ON lab_sessions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_lab_sessions_status ON lab_sessions (status);

CREATE TABLE IF NOT EXISTS provisioning_plans (
    plan_id     TEXT PRIMARY KEY,
    request_id  TEXT NOT NULL,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS showback_records (
    showback_id TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_showback_records_tenant_id ON showback_records (tenant_id);
CREATE INDEX IF NOT EXISTS idx_showback_records_session_id ON showback_records (session_id);

CREATE TABLE IF NOT EXISTS catalog_items_custom (
    catalog_item_id TEXT PRIMARY KEY,
    data            JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
