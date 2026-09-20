import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './client';
import type { CatalogIntakeSubmission } from './types';

const submission: CatalogIntakeSubmission = {
  catalog_item_id: 'agent-lab',
  display_name: 'Agent Lab',
  repository_url: 'https://github.com/example/agent-lab',
  revision: 'a'.repeat(40),
  owner: 'field-engineering',
  audience: ['solution architects'],
  duration_hours: 4,
  lab_type: 'guided_build',
  expected_scale: 25,
};

afterEach(() => vi.restoreAllMocks());

describe('catalog intake API contract', () => {
  it('uses the versioned admin collection for list and detail reads', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await api.listCatalogIntakes();
    await api.getCatalogIntake('intake/one');
    await api.getCatalogIntakePipeline('intake/one');

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/admin/catalog-intakes');
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/admin/catalog-intakes/intake%2Fone');
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/admin/catalog-intakes/intake%2Fone/pipeline');
  });

  it('posts the immutable release submission without inventing approval fields', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await api.submitCatalogIntake(submission);

    const [, options] = fetchMock.mock.calls[0] ?? [];
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/admin/catalog-intakes');
    expect(options).toMatchObject({ method: 'POST' });
    expect(JSON.parse(String(options?.body))).toEqual(submission);
  });
});
