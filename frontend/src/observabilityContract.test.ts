import { describe, expect, it } from 'vitest';
import {
  filterProvisioning,
  formatOperationalDuration,
  grafanaDrilldownUrl,
  statusTone,
} from './observabilityContract';
import type { ProvisioningObservation } from './api/types';

const lab: ProvisioningObservation = {
  order_id: 'workshop-1',
  order_type: 'workshop',
  name: 'Agent workshop',
  catalog_item_id: 'agent-lab',
  cluster_ref: 'arena',
  status: 'provisioning',
  started_at: '2026-09-08T12:00:00',
  seats_requested: 2,
  ready_seats: 1,
  failed_seats: 0,
  inflight_seats: 1,
  status_counts: { ready: 1, provisioning: 1 },
  max_ready_seconds: 90,
  oldest_inflight_seconds: 180,
  detail_url: '/workshops/workshop-1',
  seats: [],
};

describe('admin observability presentation contract', () => {
  it('filters operational labs across name, catalog and cluster', () => {
    expect(filterProvisioning([lab], 'agent')).toEqual([lab]);
    expect(filterProvisioning([lab], 'arena')).toEqual([lab]);
    expect(filterProvisioning([lab], 'xeon')).toEqual([]);
  });

  it('formats workflow durations without pretending they are telemetry', () => {
    expect(formatOperationalDuration(null)).toBe('—');
    expect(formatOperationalDuration(59)).toBe('59s');
    expect(formatOperationalDuration(180)).toBe('3m');
    expect(formatOperationalDuration(3725)).toBe('1h 2m');
  });

  it('uses consistent operational severity tones', () => {
    expect(statusTone('ready')).toBe('success');
    expect(statusTone('provisioning')).toBe('info');
    expect(statusTone('cleanup_failed')).toBe('danger');
    expect(statusTone('reclaimed')).toBe('muted');
  });

  it('builds a Grafana drill-down without losing existing dashboard variables', () => {
    expect(
      grafanaDrilldownUrl(
        'https://grafana.example/d/launchpad?orgId=1',
        lab,
      ),
    ).toBe(
      'https://grafana.example/d/launchpad?orgId=1&var-cluster=arena&var-catalog=agent-lab',
    );
    expect(grafanaDrilldownUrl(null, lab)).toBeNull();
    expect(grafanaDrilldownUrl('not a URL', lab)).toBeNull();
  });
});
