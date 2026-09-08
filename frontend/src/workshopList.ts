import type { Workshop } from './api/types';

export type WorkshopFilter =
  | 'current'
  | 'ready'
  | 'in_progress'
  | 'attention'
  | 'completed'
  | 'all';

const READY = new Set(['ready', 'active']);
const IN_PROGRESS = new Set([
  'draft',
  'capacity_checking',
  'awaiting_confirmation',
  'queued',
  'provisioning',
  'partially_ready',
  'reclaiming',
]);
const ATTENTION = new Set(['preflight_failed', 'failed', 'completed_with_errors']);

export function filterWorkshops(
  workshops: Workshop[],
  filter: WorkshopFilter,
): Workshop[] {
  return workshops.filter((workshop) => {
    if (filter === 'all') return true;
    if (filter === 'current') return workshop.status !== 'completed';
    if (filter === 'ready') return READY.has(workshop.status);
    if (filter === 'in_progress') return IN_PROGRESS.has(workshop.status);
    if (filter === 'attention') return ATTENTION.has(workshop.status);
    return workshop.status === 'completed';
  });
}

export function newestWorkshopsFirst(workshops: Workshop[]): Workshop[] {
  return workshops
    .map((workshop, index) => ({ workshop, index }))
    .sort((left, right) => {
      const leftTime = Date.parse(left.workshop.created_at || '') || 0;
      const rightTime = Date.parse(right.workshop.created_at || '') || 0;
      return rightTime - leftTime || left.index - right.index;
    })
    .map(({ workshop }) => workshop);
}
