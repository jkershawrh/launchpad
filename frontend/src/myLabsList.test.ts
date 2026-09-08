import { describe, expect, it } from 'vitest';
import type { LabSession } from './api/types';
import {
  currentLabSessions,
  historicalLabSessions,
  individualLabSessions,
  workshopSeatCount,
} from './myLabsList';

const session = (
  sessionId: string,
  status: string,
  workshopId?: string,
): LabSession => ({
  session_id: sessionId,
  request_id: `request-${sessionId}`,
  tenant_id: 'tenant-a',
  catalog_item_id: 'lab-a',
  status,
  resources: {},
  validation_results: [],
  lifecycle_events: [],
  metadata: workshopId
    ? { labels: { 'launchpad.redhat.com/workshop-id': workshopId } }
    : {},
});

describe('My Labs list', () => {
  const sessions = [
    session('individual-ready', 'ready'),
    session('individual-failed', 'validation_failed'),
    session('individual-old', 'reclaimed'),
    session('seat-1', 'ready', 'workshop-1'),
    session('seat-2', 'ready', 'workshop-1'),
  ];

  it('does not duplicate workshop seats as individual labs', () => {
    expect(individualLabSessions(sessions).map((item) => item.session_id)).toEqual([
      'individual-ready',
      'individual-failed',
      'individual-old',
    ]);
    expect(workshopSeatCount(sessions)).toBe(2);
  });

  it('shows actionable individual labs before history', () => {
    expect(currentLabSessions(sessions).map((item) => item.session_id)).toEqual([
      'individual-ready',
      'individual-failed',
    ]);
    expect(historicalLabSessions(sessions).map((item) => item.session_id)).toEqual([
      'individual-old',
    ]);
  });
});
