import type { LabSession } from './api/types';

const HISTORY_STATUSES = new Set(['expired', 'reclaimed']);

export function workshopIdForSession(session: LabSession): string | undefined {
  const labels = session.metadata?.labels;
  const value = labels?.['launchpad.redhat.com/workshop-id'];
  return typeof value === 'string' && value ? value : undefined;
}

export function individualLabSessions(sessions: LabSession[]): LabSession[] {
  return sessions.filter((session) => !workshopIdForSession(session));
}

export function currentLabSessions(sessions: LabSession[]): LabSession[] {
  return individualLabSessions(sessions).filter(
    (session) => !HISTORY_STATUSES.has(session.status),
  );
}

export function historicalLabSessions(sessions: LabSession[]): LabSession[] {
  return individualLabSessions(sessions).filter((session) =>
    HISTORY_STATUSES.has(session.status),
  );
}

export function workshopSeatCount(sessions: LabSession[]): number {
  return sessions.filter(workshopIdForSession).length;
}
