-- Durable workshop orders, per-seat state (inside data), and restart-safe
-- idempotency. The unique partial index permits orders without a key while
-- preventing duplicate keyed orders within a tenant.

CREATE TABLE IF NOT EXISTS workshops (
    workshop_id       TEXT PRIMARY KEY,
    tenant_id         TEXT NOT NULL,
    catalog_item_id   TEXT NOT NULL,
    status            TEXT NOT NULL,
    idempotency_key   TEXT,
    order_fingerprint TEXT,
    data               JSONB NOT NULL,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workshops_tenant_idempotency
    ON workshops (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workshops_tenant ON workshops (tenant_id);
CREATE INDEX IF NOT EXISTS idx_workshops_status ON workshops (status);
