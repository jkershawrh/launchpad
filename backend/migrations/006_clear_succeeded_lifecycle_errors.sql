-- A successful retry supersedes the operational error from its prior attempt.
-- Keep retry counts and fencing tokens as the durable takeover history while
-- preventing the admin view from presenting a succeeded job as still failed.
UPDATE lifecycle_jobs
SET last_error = NULL,
    updated_at = NOW()
WHERE status = 'succeeded'
  AND last_error IS NOT NULL;
