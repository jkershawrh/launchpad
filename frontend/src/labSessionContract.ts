import type { LabSession } from './api/types';

const RECLAIMABLE_SESSION_STATUSES = new Set([
  'ready',
  'active',
  'expired',
  'resetting',
  'failed',
  'validation_failed',
  'cleanup_failed',
]);

export function canReclaimSession(status: string): boolean {
  return RECLAIMABLE_SESSION_STATUSES.has(status);
}

export function workshopIdForSession(session: LabSession): string | null {
  const labels = session.metadata?.labels;
  if (!labels || typeof labels !== 'object') return null;
  const workshopId = (labels as Record<string, unknown>)[
    'launchpad.redhat.com/workshop-id'
  ];
  return typeof workshopId === 'string' && workshopId ? workshopId : null;
}
