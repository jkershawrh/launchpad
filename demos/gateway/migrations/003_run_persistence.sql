-- Run Persistence — completed run history
-- PostgreSQL 15+
-- Idempotent: safe to re-run

CREATE TABLE IF NOT EXISTS demo_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id VARCHAR(50) NOT NULL,
    run_type VARCHAR(30) NOT NULL,
    tenant_id UUID REFERENCES tenants(id),
    status VARCHAR(20) NOT NULL DEFAULT 'complete',
    summary JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_demo_runs_type ON demo_runs (run_type, completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_demo_runs_tenant ON demo_runs (tenant_id, completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_demo_runs_run_id ON demo_runs (run_id);
