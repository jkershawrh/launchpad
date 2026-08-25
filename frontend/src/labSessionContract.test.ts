import { describe, expect, it } from 'vitest';
import type { LabSession } from './api/types';
import { canReclaimSession, workshopIdForSession } from './labSessionContract';

describe('lab session reclaim contract', () => {
  it.each(['ready', 'active', 'expired', 'resetting', 'failed', 'validation_failed', 'cleanup_failed'])(
    'allows manual reclaim from %s',
    (status) => expect(canReclaimSession(status)).toBe(true),
  );

  it.each(['requested', 'provisioning', 'validating', 'reclaimed'])(
    'does not offer reclaim from %s',
    (status) => expect(canReclaimSession(status)).toBe(false),
  );

  it('finds the parent workshop from session labels', () => {
    const session = {
      metadata: {
        labels: {'launchpad.redhat.com/workshop-id': 'workshop-123'},
      },
    } as unknown as LabSession;
    expect(workshopIdForSession(session)).toBe('workshop-123');
  });
});
