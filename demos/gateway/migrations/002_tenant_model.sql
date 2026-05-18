-- Multi-Tenant Model — Partner Isolation
-- PostgreSQL 15+
-- Idempotent: safe to re-run

-- Tenants
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    tier VARCHAR(20) DEFAULT 'pilot',
    resource_quota JSONB DEFAULT '{"cpu_cores": 8, "memory_gb": 32, "gpu_count": 0}',
    config JSONB DEFAULT '{}',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- API keys (replaces single env var for multi-tenant)
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    key_hash VARCHAR(128) NOT NULL,
    label VARCHAR(100),
    scopes TEXT[] DEFAULT '{read,write}',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- Add tenant_id to existing tables
ALTER TABLE inference_requests ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE governance_decisions ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);

-- Indexes for tenant filtering
CREATE INDEX IF NOT EXISTS idx_requests_tenant ON inference_requests (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_tenant ON governance_decisions (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants (slug) WHERE active = TRUE;

-- Row-level security
ALTER TABLE inference_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance_decisions ENABLE ROW LEVEL SECURITY;

-- RLS policies (gateway sets session var per request)
DO $$ BEGIN
    CREATE POLICY tenant_isolation_requests ON inference_requests
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', true)::UUID);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY tenant_isolation_decisions ON governance_decisions
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant_id', true)::UUID);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Default internal tenant
INSERT INTO tenants (slug, display_name, tier)
VALUES ('internal', 'Intel-Red Hat Internal', 'internal')
ON CONFLICT (slug) DO NOTHING;
