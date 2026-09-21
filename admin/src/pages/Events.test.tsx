// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { EventRecord } from '../api/types';
import Events from './Events';

const event: EventRecord = {
  manifest: {
    event_id: 'intel-field-day',
    name: 'Intel Field Day',
    owner: 'field-enablement',
    technical_approver: 'platform-sre',
    exposure_policy: 'public_code',
    placement_policy: 'single_cluster_per_workshop',
    cohorts: [
      { cohort_id: 'morning', participants: 30, lab_refs: ['serve', 'agents'] },
      { cohort_id: 'afternoon', participants: 30, lab_refs: ['serve'] },
    ],
    labs: [
      { lab_ref: 'serve', catalog_id: 'intel-llm-cpu-serving', catalog_release: 'v3', required_capabilities: ['cpu'] },
      { lab_ref: 'agents', catalog_id: 'multi-agent-quickstart', catalog_release: 'v4', required_capabilities: ['cpu', 'showroom'] },
    ],
    retention: { hours: 24, starts_from: 'cohort_start' },
    approval: {
      event_owner_approved: true,
      technical_approver_approved: true,
      approved_seat_environments: 90,
      approved_retention_hours: 24,
      approved_at: '2026-09-21T15:00:00Z',
    },
  },
  capacity_preview: {
    matrix_id: 'matrix-v3',
    matrix_digest: `sha256:${'a'.repeat(64)}`,
    fleet_snapshot_id: `sha256:${'b'.repeat(64)}`,
    fleet_observed_at: '2026-09-21T14:59:00Z',
    participant_count: 60,
    seat_environments: 90,
    peak_concurrent_participants: 30,
    peak_retained_environments: 90,
    certified_capacity: 120,
    dr_reserved_capacity: 25,
    uncertified_capacity: 0,
    capacity_shortfall: 0,
    eligible: true,
    explanation: 'Event fits certified capacity.',
    allocations: [
      { cohort_id: 'morning', lab_ref: 'serve', catalog_id: 'intel-llm-cpu-serving', catalog_release: 'v3', cluster_id: 'arena', seats: 30 },
      { cohort_id: 'morning', lab_ref: 'agents', catalog_id: 'multi-agent-quickstart', catalog_release: 'v4', cluster_id: 'brutus', seats: 30 },
      { cohort_id: 'afternoon', lab_ref: 'serve', catalog_id: 'intel-llm-cpu-serving', catalog_release: 'v3', cluster_id: 'arena', seats: 30 },
    ],
    lab_capacity: [],
  },
  created_at: '2026-09-21T15:00:00Z',
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Events', () => {
  it('shows approved event demand and placement evidence without lifecycle controls', async () => {
    vi.spyOn(api, 'listEvents').mockResolvedValue([event]);

    render(<MemoryRouter><Events /></MemoryRouter>);

    expect(await screen.findByRole('heading', { name: 'Events' })).toBeInTheDocument();
    expect(screen.getByText('Intel Field Day')).toBeInTheDocument();
    expect(screen.getByText('90 seat environments')).toBeInTheDocument();
    expect(screen.getByText('2 cohorts')).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.tagName === 'P' && element.textContent === 'arena · 60 seats')).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.tagName === 'P' && element.textContent === 'brutus · 30 seats')).toBeInTheDocument();
    expect(screen.getByText('Capacity eligible')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /launch|reserve|reclaim/i })).not.toBeInTheDocument();
  });

  it('explains the empty approved-event state', async () => {
    vi.spyOn(api, 'listEvents').mockResolvedValue([]);

    render(<MemoryRouter><Events /></MemoryRouter>);

    expect(await screen.findByText('No approved events yet')).toBeInTheDocument();
  });
});
