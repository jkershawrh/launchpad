-- Durable active/active lifecycle ownership. Jobs describe desired work while
-- the aggregate lease is the fencing authority shared by provision and reclaim.

CREATE TABLE IF NOT EXISTS lifecycle_aggregate_leases (
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    active_job_id TEXT,
    owner_id TEXT,
    lease_until TIMESTAMPTZ,
    fencing_token BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (aggregate_type, aggregate_id)
);

CREATE TABLE IF NOT EXISTS lifecycle_jobs (
    job_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    cluster_ref TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 50,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    step TEXT NOT NULL DEFAULT 'queued',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 10,
    owner_id TEXT,
    lease_until TIMESTAMPTZ,
    fencing_token BIGINT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CONSTRAINT lifecycle_job_attempts_nonnegative CHECK (attempts >= 0),
    CONSTRAINT lifecycle_job_max_attempts_positive CHECK (max_attempts > 0),
    CONSTRAINT lifecycle_job_priority_nonnegative CHECK (priority >= 0),
    CONSTRAINT lifecycle_job_status_known CHECK (
        status IN ('queued', 'running', 'cancel_requested', 'cancelled', 'succeeded', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS lifecycle_jobs_claimable
    ON lifecycle_jobs (priority, next_attempt_at, created_at)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS lifecycle_jobs_aggregate
    ON lifecycle_jobs (aggregate_type, aggregate_id, created_at);

CREATE INDEX IF NOT EXISTS lifecycle_jobs_lease_expiry
    ON lifecycle_jobs (lease_until)
    WHERE status IN ('running', 'cancel_requested');
