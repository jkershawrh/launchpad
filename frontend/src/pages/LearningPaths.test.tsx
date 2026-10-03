// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import LearningPaths from './LearningPaths';

vi.mock('../api/client', () => ({ api: { listCatalog: vi.fn() } }));

const catalog = (id: string, status: 'active' | 'draft') => ({
  catalog_item_id: id,
  display_name: id,
  description: id,
  category: 'guided_build' as const,
  version: '1.0.0',
  status,
  required_capabilities: [],
  optional_capabilities: [],
  metadata: {},
});

describe('LearningPaths', () => {
  beforeEach(() => vi.resetAllMocks());
  afterEach(cleanup);

  it('shows all named tracks but only orders backend-confirmed active labs', async () => {
    vi.mocked(api.listCatalog).mockResolvedValue([
      catalog('agentic-ai-101', 'active'),
      catalog('intel-xeon6-agent-201', 'active'),
      catalog('multi-agent-quickstart', 'active'),
      catalog('agentic-ai-601', 'draft'),
      catalog('sovereign-ai-101', 'active'),
    ]);

    render(<MemoryRouter><LearningPaths /></MemoryRouter>);

    expect(await screen.findByText('Agentic AI')).toBeInTheDocument();
    expect(screen.getByText('Sovereign AI')).toBeInTheDocument();
    expect(screen.getByText('Virtualization + AI')).toBeInTheDocument();
    expect(screen.getByText('Earn the Right to Act')).toBeInTheDocument();
    expect(screen.getAllByText('Order this lab →')).toHaveLength(4);
    expect(screen.getByText('Start with the customer conversation')).toBeInTheDocument();
    expect(screen.getAllByText('Sales entry · no environment provisioned')).toHaveLength(5);
    expect(screen.getByText('Continue to Agentic AI 101 →').closest('a')).toHaveAttribute('href', '/request?catalog_item=agentic-ai-101');
    expect(screen.getByText('Continue to Virtualization + AI 101 →').closest('a')).toHaveAttribute('href', '/request?catalog_item=virtualization-ai-foundations-101');
  });

  it('fails closed when live catalog status cannot be loaded', async () => {
    vi.mocked(api.listCatalog).mockRejectedValue(new Error('unavailable'));
    render(<MemoryRouter><LearningPaths /></MemoryRouter>);

    expect(await screen.findByRole('alert')).toHaveTextContent('ordering is disabled');
    expect(screen.queryByText('Order this lab →')).not.toBeInTheDocument();
  });
});
