import type { LabSession } from './api/types';

export function newestSessionsFirst(sessions: LabSession[]): LabSession[] {
  return sessions
    .map((session, index) => ({session, index}))
    .sort((left, right) => {
      const leftTime = Date.parse(left.session.created_at || '') || 0;
      const rightTime = Date.parse(right.session.created_at || '') || 0;
      return rightTime - leftTime || left.index - right.index;
    })
    .map(({session}) => session);
}
