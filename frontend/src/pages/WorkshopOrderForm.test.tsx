// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import WorkshopOrderForm from './WorkshopOrderForm';

vi.mock('../api/client', () => ({
  api: {
    listCatalog: vi.fn(),
    listTenants: vi.fn(),
    previewWorkshop: vi.fn(),
    createWorkshopOrder: vi.fn(),
    confirmWorkshop: vi.fn(),
    getCurrentIdentity: vi.fn(),
  },
}));

describe('requester workshop order journey', () => {
  beforeEach(() => {
    vi.mocked(api.getCurrentIdentity).mockResolvedValue({
      username: 'lp-instructor-1',
      email: 'instructor@example.com',
      is_admin: false,
      identity_verified: true,
    });
    vi.mocked(api.listCatalog).mockResolvedValue([
      {
        catalog_item_id: 'multi-agent-quickstart',
        display_name: 'Build Multi-Agent AI Systems',
        description: 'Three-track guided lab',
        category: 'guided_build',
        version: '0.2.5',
        status: 'active',
        required_capabilities: ['cpu', 'showroom'],
        optional_capabilities: [],
        metadata: { max_workshop_seats: 25 },
      },
    ]);
    vi.mocked(api.listTenants).mockResolvedValue([
      {
        tenant_id: 'smoke-test-tenant',
        display_name: 'Smoke Test Tenant',
        tenant_type: 'internal',
        status: 'active',
      },
    ]);
    vi.mocked(api.previewWorkshop).mockResolvedValue({
      can_provision: true,
      reason: 'Aggregate protected capacity is available',
      seats_requested: 25,
      selected_cluster: 'arena',
      placement_reason: 'Entire workshop assigned to arena; seats will not be split',
      catalog_seat_limit: 25,
      estimated_resources: {
        cpu_millicores: 30000,
        memory_mib: 51200,
        pods: 50,
      },
    });
    vi.mocked(api.createWorkshopOrder).mockResolvedValue({
      workshop_id: 'workshop-1',
      tenant_id: 'smoke-test-tenant',
      catalog_item_id: 'multi-agent-quickstart',
      num_users: 25,
      ttl: '4h',
      status: 'awaiting_confirmation',
      seats: [],
      session_ids: [],
      cluster_ref: 'arena',
      metadata: {},
      exposure_policy: 'public_code',
      public_url: 'https://example.invalid/order/workshop-1',
      one_time_access_code: 'ALPHA-BRAVO-CHARLIE',
    });
  });

  it('uses typed preview data and keeps cluster placement operator-controlled', async () => {
    render(<MemoryRouter><WorkshopOrderForm /></MemoryRouter>);

    await screen.findByRole('option', { name: 'Build Multi-Agent AI Systems' });
    expect(screen.queryByLabelText('Workshop name')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Signed-in owner/)).toHaveValue('lp-instructor-1');
    expect(screen.getByLabelText(/^Signed-in owner/)).toHaveAttribute('readonly');
    fireEvent.change(screen.getByLabelText('Tenant'), {
      target: { value: 'smoke-test-tenant' },
    });
    fireEvent.change(screen.getByLabelText('Lab'), {
      target: { value: 'multi-agent-quickstart' },
    });
    fireEvent.change(screen.getByLabelText(/^Access/), {
      target: { value: 'public_code' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Check capacity' }));

    await screen.findByText('Execution cluster: arena');
    expect(screen.getAllByText('50')).toHaveLength(2);
    expect(screen.getByText('pod slots')).toBeInTheDocument();
    expect(api.previewWorkshop).toHaveBeenCalledWith(
      expect.objectContaining({
        tenant_id: 'smoke-test-tenant',
        catalog_item_id: 'multi-agent-quickstart',
        num_users: 25,
      }),
    );
    expect(vi.mocked(api.previewWorkshop).mock.calls[0][0]).not.toHaveProperty(
      'target_cluster',
    );
    expect(vi.mocked(api.previewWorkshop).mock.calls[0][0]).not.toHaveProperty(
      'name',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Create workshop order' }));

    await waitFor(() => {
      expect(screen.getByText('ALPHA-BRAVO-CHARLIE')).toBeInTheDocument();
    });
    expect(screen.getByText('https://example.invalid/order/workshop-1')).toBeInTheDocument();
  });

  it('excludes compatibility aliases and internal diagnostics from workshop ordering', async () => {
    vi.mocked(api.listCatalog).mockResolvedValue([
      {
        catalog_item_id: 'unrelated-lab',
        display_name: 'Unrelated Lab',
        description: 'Must not be selected by alias fallback',
        category: 'guided_build',
        version: '1.0.0',
        status: 'active',
        required_capabilities: [],
        optional_capabilities: [],
        metadata: { max_workshop_seats: 1 },
      },
      {
        catalog_item_id: 'intel-llm-cpu-serving',
        display_name: 'Serve LLMs on Intel Xeon CPUs',
        description: 'Canonical learner experience',
        category: 'guided_build',
        version: '1.0.0',
        status: 'active',
        required_capabilities: [],
        optional_capabilities: [],
        metadata: { max_workshop_seats: 5 },
      },
      {
        catalog_item_id: 'cpu-inference-serving',
        display_name: 'Legacy CPU Inference Alias',
        description: 'Compatibility alias',
        category: 'guided_build',
        version: '1.0.0',
        status: 'active',
        required_capabilities: [],
        optional_capabilities: [],
        metadata: {
          migration_mode: 'compatibility_alias',
          canonical_item_id: 'intel-llm-cpu-serving',
          max_workshop_seats: 5,
        },
      },
      {
        catalog_item_id: 'smoke-test',
        display_name: 'Platform Smoke Test',
        description: 'Internal diagnostic',
        category: 'quick_start',
        version: '1.0.0',
        status: 'active',
        required_capabilities: [],
        optional_capabilities: [],
        metadata: {
          catalog_visibility: 'internal_diagnostic',
          participant_orderable: false,
        },
      },
    ]);

    render(
      <MemoryRouter initialEntries={['/request?type=workshop&catalog_item=cpu-inference-serving']}>
        <WorkshopOrderForm />
      </MemoryRouter>,
    );

    await screen.findByRole('option', { name: 'Serve LLMs on Intel Xeon CPUs' });
    expect(screen.queryByRole('option', { name: 'Legacy CPU Inference Alias' })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Platform Smoke Test' })).not.toBeInTheDocument();
    const labSelects = screen.getAllByLabelText('Lab');
    expect(labSelects.at(-1)).toHaveValue('intel-llm-cpu-serving');
  });
});
