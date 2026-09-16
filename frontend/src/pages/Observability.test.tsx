// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { AdminObservability } from '../api/types';
import Observability from './Observability';

vi.mock('../api/client', () => ({
  api: { getAdminObservability: vi.fn(), getLifecycleHealth: vi.fn() },
}));

const snapshot: AdminObservability = {
  schema: 'launchpad.admin-observability/v1',
  generated_at: '2026-09-08T12:00:00Z',
  summary: {
    clusters_healthy: 1,
    clusters_total: 1,
    labs_active: 1,
    seats_active: 1,
    seats_inflight: 0,
    seats_attention: 0,
  },
  clusters: [{
    cluster_id: 'arena',
    cluster_name: 'Arena',
    healthy: true,
    eligible: true,
    available_cpu_millicores: 80000,
    available_memory_mib: 262144,
    available_pods: 150,
    active_sessions: 1,
    active_workshops: 1,
    active_seats: 1,
  }],
  provisioning: [{
    order_id: 'workshop-1',
    order_type: 'workshop',
    name: 'Agent workshop',
    catalog_item_id: 'agent-lab',
    cluster_ref: 'arena',
    status: 'ready',
    seats_requested: 1,
    ready_seats: 1,
    failed_seats: 0,
    inflight_seats: 0,
    status_counts: { ready: 1 },
    max_ready_seconds: 90,
    seats: [{
      seat_number: 1,
      session_id: 'session-1',
      namespace: 'agent-seat-1',
      status: 'ready',
      provisioning_seconds: 90,
      resolution_state: 'none',
      detail_url: '/sessions/session-1',
      resource_usage: {
        available: true,
        cpu_millicores: 425,
        memory_mib: 768,
        pod_count: 3,
        ready_pods: 3,
        restarts: 0,
        terminal_reconnects: null,
        observed_at: '2026-09-08T12:00:00Z',
      },
    }],
    detail_url: '/workshops/workshop-1',
  }],
  inflight: [],
  resolution: [],
  grafana: {
    configured: true,
    url: 'https://grafana.example/d/launchpad',
    purpose: 'Historical resource, network, and latency telemetry',
  },
  llm: {
    summary: {
      models_configured: 1,
      models_running: 1,
      models_healthy: 1,
      requests_observed: 2,
      avg_latency_ms: 1000,
      p95_latency_ms: 1200,
      errors: 0,
      rate_limited: 0,
      estimated_tokens: 100,
      input_tokens: 40,
      output_tokens: 60,
      total_tokens: 100,
      token_measurement: 'exact',
      attributed_requests: 2,
    },
    models: [{
      model_id: 'granite',
      display_name: 'Granite',
      status: 'healthy',
      desired_replicas: 2,
      ready_replicas: 2,
      route: 'LiteLLM: granite',
      backend: 'fleet-llm-d/vllm-granite',
    }],
    attribution: [{
      order_id: 'workshop-1',
      order_type: 'workshop',
      catalog_item_id: 'agent-lab',
      cluster_ref: 'arena',
      seat_number: 1,
      session_id: 'session-1',
      namespace: 'agent-seat-1',
      model_id: 'granite',
      requests: 2,
      avg_latency_ms: 1000,
      p95_latency_ms: 1200,
      errors: 0,
      rate_limited: 0,
      estimated_tokens: 100,
      input_tokens: 40,
      output_tokens: 60,
      total_tokens: 100,
      token_measurement: 'exact',
      outcomes: { success: 2 },
    }],
    telemetry_gaps: [],
  },
};

afterEach(() => vi.clearAllMocks());

describe('operator observability component', () => {
  it('renders control-room tabs with lab-selected seat tiles', async () => {
    vi.mocked(api.getAdminObservability).mockResolvedValue(snapshot);
    vi.mocked(api.getLifecycleHealth).mockResolvedValue({
      enabled: true,
      summary: {
        queued: 1,
        running: 1,
        cancel_requested: 0,
        cancelled: 0,
        succeeded: 4,
        failed: 0,
        reclaim_pending: 0,
        takeovers: 1,
        expired_leases: 0,
        oldest_pending_age_seconds: 12,
      },
      jobs: [],
    });
    const view = render(<MemoryRouter><Observability /></MemoryRouter>);

    expect(await screen.findByText('Lab observability')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Labs & seats' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'AI models' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Clusters' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Events & alerts' })).toBeInTheDocument();
    expect(screen.getByLabelText('Select a lab')).toHaveValue('workshop-1');
    expect(screen.getByText('Seat 01')).toBeInTheDocument();
    expect(screen.getByText('agent-seat-1')).toBeInTheDocument();
    expect(screen.getByText('425m')).toBeInTheDocument();
    expect(screen.getByText('768 MiB')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'AI models' }));
    expect(screen.getByText('Granite')).toBeInTheDocument();
    expect(screen.getByText('2 / 2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Clusters' }));
    expect(screen.getByText('Arena')).toBeInTheDocument();
    expect(screen.getByText('80 cores')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Events & alerts' }));
    expect(screen.getByText('Lifecycle and platform events')).toBeInTheDocument();
    await waitFor(() => expect(api.getAdminObservability).toHaveBeenCalledTimes(1));
    view.unmount();
  });
});
