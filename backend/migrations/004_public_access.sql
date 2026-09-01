-- Passwordless public access records. Plaintext instructor codes and browser
-- tokens are never stored; only Argon2id/SHA-256 hashes live in durable state.
CREATE TABLE IF NOT EXISTS access_policies (
    order_id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS participant_identities (
    participant_id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS participant_identity_email
    ON participant_identities ((lower(data->>'normalized_email')));

CREATE TABLE IF NOT EXISTS participant_entitlements (
    entitlement_id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS participant_order_entitlement
    ON participant_entitlements ((data->>'order_id'), (data->>'participant_id'));
CREATE UNIQUE INDEX IF NOT EXISTS active_order_seat
    ON participant_entitlements ((data->>'order_id'), (data->>'seat_ref'))
    WHERE data->>'status' <> 'revoked';

CREATE TABLE IF NOT EXISTS access_audit_events (
    event_id BIGSERIAL PRIMARY KEY,
    order_id TEXT,
    event_type TEXT NOT NULL,
    actor_hash TEXT,
    outcome TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS access_sessions (
    session_id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS access_claim_failures (
    failure_id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL,
    email_hash TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS access_claim_failures_window
    ON access_claim_failures (order_id, created_at);
