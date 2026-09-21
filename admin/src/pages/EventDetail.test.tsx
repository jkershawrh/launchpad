// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { EventRecord, EventStatusResult } from '../api/types';
import EventDetail from './EventDetail';

const event: EventRecord = {
  manifest: {
    event_id: 'field-day', name: 'Intel Field Day', owner: 'field', technical_approver: 'sre',
    exposure_policy: 'public_code', placement_policy: 'single_cluster_per_workshop',
    cohorts: [{ cohort_id: 'morning', participants: 30, lab_refs: ['serve', 'agents'] }],
    labs: [
      { lab_ref: 'serve', catalog_id: 'intel-llm-cpu-serving', catalog_release: 'v3', required_capabilities: ['cpu'] },
      { lab_ref: 'agents', catalog_id: 'multi-agent-quickstart', catalog_release: 'v4', required_capabilities: ['showroom'] },
    ],
    retention: { hours: 24, starts_from: 'cohort_start' },
    approval: { event_owner_approved: true, technical_approver_approved: true, approved_seat_environments: 60, approved_retention_hours: 24, approved_at: '2026-09-21T15:00:00Z' },
  },
  capacity_preview: {
    matrix_id: 'matrix-v3', matrix_digest: `sha256:${'a'.repeat(64)}`, fleet_snapshot_id: `sha256:${'b'.repeat(64)}`,
    fleet_observed_at: '2026-09-21T14:59:00Z', participant_count: 30, seat_environments: 60,
    peak_concurrent_participants: 30, peak_retained_environments: 60, certified_capacity: 90,
    dr_reserved_capacity: 25, uncertified_capacity: 0, capacity_shortfall: 0, eligible: true,
    explanation: 'Event fits certified capacity.', allocations: [], lab_capacity: [],
  },
  created_at: '2026-09-21T15:00:00Z',
};

const status: EventStatusResult = {
  event_id: 'field-day', state: 'ready', reservation_complete: true,
  summary: { reservations: 2, workshops: 2, lifecycle_jobs: 2, seats: 60, ready_seats: 60, failed_seats: 0, reclaimed_seats: 0, public_workshops_active: 2 },
  workshops: [
    { reservation_id: 'r1', cohort_id: 'morning', lab_ref: 'serve', catalog_id: 'intel-llm-cpu-serving', catalog_release: 'v3', cluster_ref: 'arena', seats: 30, reservation_status: 'consumed', workshop_id: 'w1', workshop_status: 'ready', lifecycle_job_id: 'j1', lifecycle_job_status: 'succeeded', ready_seats: 30, failed_seats: 0, reclaimed_seats: 0, public_access_state: 'active', public_url: 'https://labs.example.io/labs/serve' },
    { reservation_id: 'r2', cohort_id: 'morning', lab_ref: 'agents', catalog_id: 'multi-agent-quickstart', catalog_release: 'v4', cluster_ref: 'brutus', seats: 30, reservation_status: 'consumed', workshop_id: 'w2', workshop_status: 'ready', lifecycle_job_id: 'j2', lifecycle_job_status: 'succeeded', ready_seats: 30, failed_seats: 0, reclaimed_seats: 0, public_access_state: 'active', public_url: 'https://labs.example.io/labs/agents' },
  ],
  observed_at: '2026-09-21T16:00:00Z',
};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('EventDetail', () => {
  it('unifies readiness, access, placement, support, and evidence without lifecycle controls', async () => {
    vi.spyOn(api, 'getEvent').mockResolvedValue(event);
    vi.spyOn(api, 'getEventStatus').mockResolvedValue(status);
    render(<MemoryRouter initialEntries={['/events/field-day']}><Routes><Route path="/events/:eventId" element={<EventDetail />} /></Routes></MemoryRouter>);

    expect(await screen.findByRole('heading', { name: 'Intel Field Day' })).toBeInTheDocument();
    expect(screen.getByText('60 / 60 ready')).toBeInTheDocument();
    expect(screen.getByText('No failed seats')).toBeInTheDocument();
    expect(screen.getByText('arena')).toBeInTheDocument();
    expect(screen.getByText('brutus')).toBeInTheDocument();
    expect(screen.getAllByText('Public access active')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Open intel-llm-cpu-serving' })).toHaveAttribute('href', 'https://labs.example.io/labs/serve');
    expect(screen.getByText('matrix-v3')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /launch|reserve|activate|reclaim/i })).not.toBeInTheDocument();
  });
});
