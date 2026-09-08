import type { LabSession } from './api/types';

const TERMINAL_STATUSES = new Set([
  'ready',
  'active',
  'validation_failed',
  'failed',
  'cleanup_failed',
  'rejected',
]);

export function usesDurableLifecycle(session: LabSession): boolean {
  return typeof session.metadata?.lifecycle_job_id === 'string'
    && session.metadata.lifecycle_job_id.length > 0;
}

export function isProvisioningTerminal(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
}
