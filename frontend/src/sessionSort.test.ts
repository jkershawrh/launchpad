import { describe, expect, it } from 'vitest';
import type { LabSession } from './api/types';
import { newestSessionsFirst } from './sessionSort';

describe('My Labs ordering', () => {
  it('sorts sessions newest to oldest without mutating the API result', () => {
    const sessions = [
      {session_id: 'older', created_at: '2026-08-24T10:00:00Z'},
      {session_id: 'newest', created_at: '2026-08-25T20:00:00Z'},
      {session_id: 'middle', created_at: '2026-08-25T12:00:00Z'},
    ] as LabSession[];

    expect(newestSessionsFirst(sessions).map((session) => session.session_id)).toEqual([
      'newest', 'middle', 'older',
    ]);
    expect(sessions[0].session_id).toBe('older');
  });

  it('keeps missing timestamps stable at the end', () => {
    const sessions = [
      {session_id: 'missing-a'},
      {session_id: 'dated', created_at: '2026-08-25T20:00:00Z'},
      {session_id: 'missing-b'},
    ] as LabSession[];

    expect(newestSessionsFirst(sessions).map((session) => session.session_id)).toEqual([
      'dated', 'missing-a', 'missing-b',
    ]);
  });
});
