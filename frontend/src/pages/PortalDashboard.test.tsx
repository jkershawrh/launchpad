// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import PortalDashboard from './PortalDashboard';

vi.mock('../api/client', () => ({
  api: {
    listCatalog: vi.fn(),
    listSessions: vi.fn(),
    getShowback: vi.fn(),
  },
}));

describe('external portal dashboard', () => {
  beforeEach(() => {
    vi.mocked(api.listCatalog).mockResolvedValue([
      {
        catalog_item_id: 'smoke-test',
        display_name: 'Smoke Test',
        description: 'A small test lab',
        category: 'quick_start',
        version: '1.0',
        status: 'active',
        required_capabilities: [],
        optional_capabilities: [],
      },
    ]);
    vi.mocked(api.listSessions).mockResolvedValue([
      {
        session_id: 'session-1',
        request_id: 'request-1',
        tenant_id: 'partner-a',
        catalog_item_id: 'smoke-test',
        status: 'active',
        resources: {},
        validation_results: [],
        lifecycle_events: [],
      },
    ]);
    vi.mocked(api.getShowback).mockResolvedValue({
      showback_id: 'showback-1',
      tenant_id: 'partner-a',
      session_id: 'session-1',
      catalog_item_id: 'smoke-test',
      duration_seconds: 60,
      model_requests: 42,
      estimated_tokens: 100,
      gaudi_endpoint_requests: 0,
    });
  });

  it('renders the self-service summary and primary journeys from API data', async () => {
    render(<MemoryRouter><PortalDashboard /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: /build, launch, and manage/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /request a lab/i })).toHaveAttribute('href', '/request');

    await waitFor(() => expect(screen.getByText('42')).toBeInTheDocument());
    expect(screen.getByText('smoke-test')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Account summary' })).getAllByText('1')).toHaveLength(2);
  });
});
