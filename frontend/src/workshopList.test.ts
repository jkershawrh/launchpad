import { describe, expect, it } from 'vitest';
import type { Workshop } from './api/types';
import { filterWorkshops, newestWorkshopsFirst } from './workshopList';

const workshop = (status: string, createdAt: string): Workshop => ({
  workshop_id: `${status}-${createdAt}`,
  tenant_id: 'tenant-a',
  catalog_item_id: 'lab-a',
  num_users: 25,
  ttl: '8h',
  status,
  seats: [],
  session_ids: [],
  metadata: {},
  created_at: createdAt,
});

describe('workshop list', () => {
  const items = [
    workshop('completed', '2026-09-08T12:00:00Z'),
    workshop('ready', '2026-09-08T11:00:00Z'),
    workshop('provisioning', '2026-09-08T10:00:00Z'),
    workshop('completed_with_errors', '2026-09-08T09:00:00Z'),
  ];

  it('defaults to every workshop except fully completed orders', () => {
    expect(filterWorkshops(items, 'current').map((item) => item.status)).toEqual([
      'ready',
      'provisioning',
      'completed_with_errors',
    ]);
  });

  it('supports operational status selections', () => {
    expect(filterWorkshops(items, 'ready')).toHaveLength(1);
    expect(filterWorkshops(items, 'in_progress')).toHaveLength(1);
    expect(filterWorkshops(items, 'attention')).toHaveLength(1);
    expect(filterWorkshops(items, 'completed')).toHaveLength(1);
    expect(filterWorkshops(items, 'all')).toHaveLength(4);
  });

  it('orders newest workshop orders first', () => {
    expect(newestWorkshopsFirst([...items].reverse()).map((item) => item.status)).toEqual([
      'completed',
      'ready',
      'provisioning',
      'completed_with_errors',
    ]);
  });
});
