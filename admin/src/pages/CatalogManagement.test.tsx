// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';
import CatalogManagement from './CatalogManagement';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const candidate: CatalogItem = {
  catalog_item_id: 'virtualization-ai-201',
  display_name: 'Virtualization + AI 201: Author and Qualify the Contract',
  description: 'Qualify a VM-to-AI contract.',
  category: 'guided_build',
  version: '0.1.0',
  status: 'draft',
  required_capabilities: ['openshift-virtualization'],
  optional_capabilities: [],
  metadata: {
    certification_stage: 'one-seat-internal-certified',
    max_workshop_seats: 1,
    allowed_exposure_policies: ['internal'],
    activation_blockers: ['External public-code certification remains incomplete.'],
  },
};

describe('CatalogManagement', () => {
  it('shows candidate certification and prevents a blocked draft from being activated', async () => {
    vi.spyOn(api, 'listCatalog').mockResolvedValue([candidate]);

    render(<CatalogManagement />);

    expect(await screen.findByText(candidate.display_name)).toBeInTheDocument();
    expect(screen.getByText('one seat internal certified')).toBeInTheDocument();
    expect(screen.getByText('1 activation blocker')).toBeInTheDocument();
    expect(screen.getByText('internal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Certification gated' })).toBeDisabled();
  });
});
