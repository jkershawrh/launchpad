// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import LabRequestForm from './LabRequestForm';

const navigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});

vi.mock('../api/client', () => ({
  api: {
    listCatalog: vi.fn(),
    listTenants: vi.fn(),
    listBrandingProfiles: vi.fn(),
    getCurrentIdentity: vi.fn(),
    createLabRequest: vi.fn(),
    provisionLabToReady: vi.fn(),
    listAvailableModels: vi.fn(),
  },
}));

describe('individual lab request journey', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.listCatalog).mockResolvedValue([{
      catalog_item_id: 'agentic-ai-101',
      display_name: 'Agentic AI 101',
      description: 'Understand agentic workflows',
      category: 'guided_build',
      version: '1.0.0',
      status: 'active',
      required_capabilities: [],
      optional_capabilities: [],
      default_hardware_profile: 'xeon-basic',
      metadata: { allowed_exposure_policies: ['internal', 'public_code'] },
    }]);
    vi.mocked(api.listTenants).mockResolvedValue([{
      tenant_id: 'flightpath-candidate',
      display_name: 'Flightpath Candidate',
      tenant_type: 'internal',
      status: 'active',
    }]);
    vi.mocked(api.listBrandingProfiles).mockResolvedValue([]);
    vi.mocked(api.getCurrentIdentity).mockResolvedValue({
      username: 'instructor-1',
      is_admin: false,
      identity_verified: true,
    });
  });

  it('shows a public individual lab code before provisioning and continues only after confirmation', async () => {
    vi.mocked(api.createLabRequest).mockResolvedValue({
      request_id: 'request-1',
      tenant_id: 'flightpath-candidate',
      requester_id: 'instructor-1',
      catalog_item_id: 'agentic-ai-101',
      requested_mode: 'guided_build',
      persistence: 'ephemeral',
      status: 'approved',
      created_at: '2026-10-05T12:00:00Z',
      exposure_policy: 'public_code',
      public_url: 'https://labs.example.test/labs/agentic-ai-101-request-1',
      one_time_access_code: 'ALPHA-BRAVO-CHARLIE',
    });
    vi.mocked(api.provisionLabToReady).mockResolvedValue({
      session_id: 'session-1',
      request_id: 'request-1',
      tenant_id: 'flightpath-candidate',
      catalog_item_id: 'agentic-ai-101',
      status: 'ready',
      resources: {},
      validation_results: [],
      lifecycle_events: [],
    });

    render(<MemoryRouter initialEntries={['/request?catalog_item=agentic-ai-101']}><LabRequestForm /></MemoryRouter>);

    await screen.findByRole('option', { name: 'Agentic AI 101 (guided build)' });
    fireEvent.change(screen.getByLabelText('Tenant'), { target: { value: 'flightpath-candidate' } });
    fireEvent.change(screen.getByLabelText('Access'), { target: { value: 'public_code' } });
    fireEvent.click(screen.getByRole('button', { name: 'Launch Lab' }));

    expect(await screen.findByText('ALPHA-BRAVO-CHARLIE')).toBeInTheDocument();
    expect(screen.getByText('https://labs.example.test/labs/agentic-ai-101-request-1')).toBeInTheDocument();
    expect(api.provisionLabToReady).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'I saved the code — start provisioning' }));
    await waitFor(() => expect(api.provisionLabToReady).toHaveBeenCalledWith('request-1'));
    expect(navigate).toHaveBeenCalledWith('/sessions/session-1');
  });
});
