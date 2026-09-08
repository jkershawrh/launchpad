import { describe, expect, it } from 'vitest';
import type { LabSession } from './api/types';
import {
  isProvisioningTerminal,
  usesDurableLifecycle,
} from './sessionProvisioning';

describe('durable session provisioning contract', () => {
  it('detects a queued lifecycle session from its persisted job reference', () => {
    const session = {
      status: 'requested',
      metadata: { lifecycle_job_id: 'job-1' },
    } as unknown as LabSession;

    expect(usesDurableLifecycle(session)).toBe(true);
    expect(isProvisioningTerminal(session.status)).toBe(false);
  });

  it.each(['ready', 'active', 'validation_failed', 'failed', 'cleanup_failed', 'rejected'])(
    'treats %s as terminal for polling',
    (status) => expect(isProvisioningTerminal(status)).toBe(true),
  );

  it.each(['requested', 'provisioning', 'validating'])(
    'keeps polling while status is %s',
    (status) => expect(isProvisioningTerminal(status)).toBe(false),
  );
});
