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
    metadata: {
      allowed_exposure_policies: ['internal'],
      intake_quality: {
        schema_version: 'launchpad.redhat.com/catalog-intake-quality/v1',
        business_solution: {
          status: 'review-required',
          readme_present: true,
          title: 'Build an Agent Lab',
          action_oriented_title: true,
          required_sections_present: true,
          missing_sections: [],
          business_language_present: true,
          human_review_required: true,
        },
        artifacts: {
          validation_matrix: { path: 'tests/validation_matrix.yaml', status: 'present-valid', entry_count: 5 },
          claim_registry: { path: 'tests/claim_registry.yaml', status: 'missing', entry_count: 0 },
          benchmark_rubric: { path: 'tests/benchmark_rubric.yaml', status: 'present-valid', entry_count: 3 },
          publication_test: { path: 'tests/publication/test_readme.py', status: 'present' },
          makefile: { path: 'Makefile', status: 'present' },
          ci_workflows: { path: '.github/workflows', status: 'present' },
        },
        showroom: {
          page_count: 4,
          hands_on_module_count: 3,
          execute_block_count: 8,
          see_section_count: 3,
          verification_section_count: 3,
          key_takeaway_count: 3,
          thin_modules: [],
        },
        capacity_proposal: {
          status: 'review-required',
          inference_mode: 'remote-endpoint',
          framework_signals: ['openai'],
          declared_models: [],
          explicit_resource_envelopes: 0,
          measurement_required_before_placement: true,
        },
        security_summary: {
          status: 'review-required',
          mutable_image_count: 1,
          cluster_scoped_resource_count: 0,
          privileged_finding_count: 0,
          secret_manifest_count: 0,
          unparsed_manifest_count: 0,
          secret_values_included: false,
        },
        portfolio_overlap: {
          status: 'not-run',
          reason: 'A pinned versioned portfolio inventory was not supplied.',
          mutable_live_org_scan_allowed: false,
        },
        gate: {
          status: 'blocked',
          blocking_findings: ['tests/claim_registry.yaml is missing or invalid'],
        },
        authority: {
          mode: 'analysis-only',
          may_modify_source: false,
          may_publish_catalog: false,
          may_provision: false,
          may_certify: false,
        },
      },
    },
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
  actions: { approve_source: false, run_discovery: false, generate_draft: false, run_one_seat_certification: false, request_review: false, promote: false },
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
    expect(screen.getByText('Source discovery')).toBeInTheDocument();
    expect(screen.getByText('discovery-not-run')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Catalog draft preview' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Quickstart quality review' })).toBeInTheDocument();
    expect(screen.getByText('Blocked')).toBeInTheDocument();
    expect(screen.getByText('tests/claim_registry.yaml is missing or invalid')).toBeInTheDocument();
    expect(screen.getByText('3 hands-on modules')).toBeInTheDocument();
    expect(screen.getByText('Remote endpoint')).toBeInTheDocument();
    expect(screen.getByText('1 mutable image')).toBeInTheDocument();
    expect(screen.getByText(/Analysis only/)).toBeInTheDocument();
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
