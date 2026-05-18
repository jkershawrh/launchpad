-- Intel-Red Hat AI Inference Platform — Initial Schema
-- PostgreSQL 15+
-- Idempotent: safe to re-run

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS inference_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task VARCHAR(50) NOT NULL,
    model VARCHAR(255),
    model_size_b REAL,
    backend VARCHAR(100) NOT NULL,
    accelerator VARCHAR(50),
    status VARCHAR(20) NOT NULL,
    latency_ms REAL,
    cost_estimate REAL,
    reason TEXT,
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS governance_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID REFERENCES inference_requests(id),
    source VARCHAR(50),
    intent VARCHAR(100),
    risk_score REAL,
    risk_level VARCHAR(20),
    decision VARCHAR(30) NOT NULL,
    reason TEXT,
    evidence JSONB,
    approved_by VARCHAR(100),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backends (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    url TEXT NOT NULL,
    accelerator VARCHAR(50),
    capabilities TEXT[],
    cost_per_1k_tokens REAL DEFAULT 0,
    max_concurrent INTEGER DEFAULT 10,
    healthy BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS routing_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task VARCHAR(50) NOT NULL,
    backend_id UUID REFERENCES backends(id),
    priority INTEGER DEFAULT 0,
    condition_type VARCHAR(20),
    condition_json JSONB,
    reason TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID,
    action VARCHAR(20) NOT NULL,
    changes JSONB,
    performed_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_requests_created_at ON inference_requests (created_at);
CREATE INDEX IF NOT EXISTS idx_requests_task_backend ON inference_requests (task, backend);
CREATE INDEX IF NOT EXISTS idx_requests_status ON inference_requests (status);
CREATE INDEX IF NOT EXISTS idx_requests_task_backend_created ON inference_requests (task, backend, created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON governance_decisions (created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_decision ON governance_decisions (decision);
CREATE INDEX IF NOT EXISTS idx_decisions_source ON governance_decisions (source);
CREATE INDEX IF NOT EXISTS idx_backends_name ON backends (name);
CREATE INDEX IF NOT EXISTS idx_backends_accelerator ON backends (accelerator);
CREATE INDEX IF NOT EXISTS idx_routing_rules_task ON routing_rules (task);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_decisions_request_id ON governance_decisions (request_id, created_at);

-- Composite index for analytics queries
CREATE INDEX IF NOT EXISTS idx_requests_status_created ON inference_requests (status, created_at);

-- Migration tracking table
CREATE TABLE IF NOT EXISTS applied_migrations (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT NOW()
);

-- Updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER update_backends_updated_at
    BEFORE UPDATE ON backends
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
