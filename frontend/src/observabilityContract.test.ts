import { describe, expect, it } from 'vitest';
import {
  clusterHealth,
  filterProvisioning,
  formatOperationalDuration,
  grafanaDrilldownUrl,
  modelHealth,
  seatHealth,
  statusTone,
} from './observabilityContract';
import type {
  ClusterObservation,
  LlmAttributionObservation,
  LlmModelObservation,
  ProvisioningObservation,
  SeatObservation,
} from './api/types';

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

  it('grades a seat from lifecycle and attributed AI traffic', () => {
    const seat: SeatObservation = {
      seat_number: 1,
      session_id: 'session-1',
      namespace: 'seat-1',
      status: 'ready',
      provisioning_seconds: 90,
      resolution_state: 'none',
      resource_usage: { available: true, pod_count: 3, ready_pods: 3, restarts: 0 },
    };
    const traffic: LlmAttributionObservation = {
      order_id: 'workshop-1', order_type: 'workshop', catalog_item_id: 'agent-lab',
      cluster_ref: 'arena', seat_number: 1, session_id: 'session-1', namespace: 'seat-1',
      model_id: 'granite', requests: 4, avg_latency_ms: 1_000, p95_latency_ms: 1_500,
      errors: 0, rate_limited: 0, estimated_tokens: 200, input_tokens: 80,
      output_tokens: 120, total_tokens: 200, token_measurement: 'exact', outcomes: { success: 4 },
    };
    expect(seatHealth(seat, [traffic]).tone).toBe('success');
    expect(seatHealth(seat, [{ ...traffic, rate_limited: 1 }]).tone).toBe('warning');
    expect(seatHealth({ ...seat, resource_usage: { available: true, pod_count: 3, ready_pods: 2, restarts: 1 } }, []).tone).toBe('warning');
    expect(seatHealth({ ...seat, status: 'validation_failed' }, []).tone).toBe('danger');
  });

  it('grades model replica pressure and cluster headroom', () => {
    const model: LlmModelObservation = {
      model_id: 'granite', display_name: 'Granite', status: 'healthy', hardware: 'Intel Xeon',
      desired_replicas: 4, ready_replicas: 4, route: 'direct', backend: 'fleet/granite',
    };
    expect(modelHealth(model, []).tone).toBe('success');
    expect(modelHealth({ ...model, ready_replicas: 3 }, []).tone).toBe('warning');
    expect(modelHealth({ ...model, ready_replicas: 0 }, []).tone).toBe('danger');

    const cluster: ClusterObservation = {
      cluster_id: 'arena', cluster_name: 'Arena', healthy: true, eligible: true,
      available_cpu_millicores: 80_000, available_memory_mib: 262_144,
      available_pods: 150, active_sessions: 30, active_workshops: 1, active_seats: 30,
    };
    expect(clusterHealth(cluster).tone).toBe('success');
    expect(clusterHealth({ ...cluster, available_pods: 20 }).tone).toBe('warning');
    expect(clusterHealth({ ...cluster, healthy: false }).tone).toBe('danger');
  });
});
