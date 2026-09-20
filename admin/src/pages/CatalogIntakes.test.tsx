// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { CatalogIntakeDraft } from '../api/types';
import CatalogIntakeDetail from './CatalogIntakeDetail';
import CatalogIntakes from './CatalogIntakes';
import NewCatalogIntake from './NewCatalogIntake';

const draft: CatalogIntakeDraft = {
  intake_id: 'intake-agent-lab',
  state: 'draft',
  orderable: false,
  promotion_eligible: false,
  storage_scope: 'durable-postgres',
  requested: {
    catalog_item_id: 'agent-lab',
    display_name: 'Agent Lab',
    repository_url: 'https://github.com/example/agent-lab',
    revision: 'a'.repeat(40),
    owner: 'field-engineering',
    audience: ['solution architects'],
    duration_hours: 4,
    lab_type: 'guided_build',
    expected_scale: 25,
  },
  defaults: { exposure_policies: ['internal'], maximum_seats: 1 },
  blockers: ['evidence-not-run', 'targets-unverified'],
  evidence: {
    status: 'not-run',
    artifacts: [],
    required_gates: ['contract', 'component', 'live-certification'],
  },
  supported_targets: [],
  target_status: 'unverified',
  release_identity: {
    repository_url: 'https://github.com/example/agent-lab',
    revision: 'a'.repeat(40),
  },
  approval_history: [],
  rollback: { status: 'not-defined', metadata: {} },
  discovery: {
    status: 'passed',
    attempt_id: 'attempt-001',
    output_hash: `sha256:${'c'.repeat(64)}`,
    worker_image_digest: `sha256:${'b'.repeat(64)}`,
    files_scanned: 12,
    bytes_scanned: 4096,
    cleanup_verified: true,
  },
  catalog_preview: {
    catalog_item_id: 'agent-lab',
    display_name: 'Agent Lab',
    description: 'Repository-discovered onboarding draft.',
    category: 'guided_build',
    version: '0.1.0',
    status: 'draft',
    required_capabilities: ['openshift', 'showroom'],
    optional_capabilities: [],
    metadata: { allowed_exposure_policies: ['internal'] },
  },
};

const pipeline = {
  schema_version: 'launchpad.redhat.com/catalog-intake-pipeline/v1' as const,
  intake_id: draft.intake_id,
  source_standard: 'quickstart-repository' as const,
  metadata_policy: 'discover-from-source' as const,
  current_stage: 'submitted' as const,
  orderable: false as const,
  promotion_eligible: false as const,
  durable_storage: true,
  isolated_worker_available: false,
  stages: [
    { stage_id: 'submitted', label: 'Submitted', status: 'current' as const, gate_ids: ['source'] },
    { stage_id: 'certified', label: 'Certified', status: 'locked' as const, gate_ids: ['evidence'] },
  ],
  gates: [
    { gate_id: 'source', label: 'Source discovery', status: 'not-run' as const, required_evidence: ['manifest'], blockers: ['discovery-not-run'] },
  ],
  actions: { run_discovery: false, generate_draft: false, run_one_seat_certification: false, request_review: false, promote: false },
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('CatalogIntakes', () => {
  it('lists draft submissions and exposes a clear new-intake path', async () => {
    vi.spyOn(api, 'listCatalogIntakes').mockResolvedValue([draft]);

    render(
      <MemoryRouter>
        <CatalogIntakes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: 'Catalog intake' })).toBeInTheDocument();
    expect(screen.getByText('Agent Lab', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.getByText('Catalog draft review')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'New intake submission' })).toHaveAttribute(
      'href',
      '/intakes/new',
    );
  });

  it('renders contract boundaries and disables unavailable release actions', async () => {
    vi.spyOn(api, 'getCatalogIntake').mockResolvedValue(draft);
    vi.spyOn(api, 'getCatalogIntakePipeline').mockResolvedValue(pipeline);

    render(
      <MemoryRouter initialEntries={['/intakes/intake-agent-lab']}>
        <Routes>
          <Route path="/intakes/:intakeId" element={<CatalogIntakeDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: 'Agent Lab' })).toBeInTheDocument();
    expect(screen.getByText('evidence-not-run')).toBeInTheDocument();
    expect(screen.getByText('No targets verified')).toBeInTheDocument();
    expect(screen.getByText('1 seat')).toBeInTheDocument();
    expect(screen.getByText('No approvals recorded')).toBeInTheDocument();
    expect(screen.getByText('Rollback not defined')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Discovery result' })).toBeInTheDocument();
    expect(screen.getByText('12 files scanned')).toBeInTheDocument();
    expect(screen.getByText('Stage: Catalog draft review')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Catalog draft preview' })).toBeInTheDocument();
    expect(screen.getByText('openshift, showroom')).toBeInTheDocument();
    expect(screen.getByText('Durable PostgreSQL')).toBeInTheDocument();
    expect(screen.getByText('Submitted')).toBeInTheDocument();
    expect(screen.getByText('Certified')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run certification' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Promote to catalog' })).toBeDisabled();
    await waitFor(() => expect(api.getCatalogIntake).toHaveBeenCalledWith('intake-agent-lab'));
    expect(api.getCatalogIntakePipeline).toHaveBeenCalledWith('intake-agent-lab');
  });

  it('submits only the declared intake fields and navigates to the draft', async () => {
    vi.spyOn(api, 'submitCatalogIntake').mockResolvedValue(draft);
    render(
      <MemoryRouter initialEntries={['/intakes/new']}>
        <Routes>
          <Route path="/intakes/new" element={<NewCatalogIntake />} />
          <Route path="/intakes/:intakeId" element={<p>Draft opened</p>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/canonical source of lab metadata/i)).toBeInTheDocument();
    expect(screen.getByText(/Launchpad draft hints/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Catalog item ID'), { target: { value: 'agent-lab' } });
    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Agent Lab' } });
    fireEvent.change(screen.getByLabelText('HTTPS GitHub repository'), { target: { value: 'https://github.com/example/agent-lab' } });
    fireEvent.change(screen.getByLabelText(/Immutable Git SHA/), { target: { value: 'a'.repeat(40) } });
    fireEvent.change(screen.getByLabelText('Owner'), { target: { value: 'field-engineering' } });
    fireEvent.change(screen.getByLabelText(/Audience/), { target: { value: 'solution architects, partners' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create intake draft' }));

    expect(await screen.findByText('Draft opened')).toBeInTheDocument();
    expect(api.submitCatalogIntake).toHaveBeenCalledWith(expect.objectContaining({
      revision: 'a'.repeat(40),
      audience: ['solution architects', 'partners'],
      expected_scale: 25,
    }));
  });
});
