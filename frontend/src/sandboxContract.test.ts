import { describe, expect, it } from 'vitest';
import type { CatalogItem } from './api/types';
import { resolveOpenSandbox } from './sandboxContract';

const item = (catalog_item_id: string, category: CatalogItem['category'], status = 'active'): CatalogItem => ({
  catalog_item_id,
  display_name: catalog_item_id,
  description: '',
  category,
  version: '1',
  status,
  required_capabilities: [],
  optional_capabilities: [],
});

describe('open sandbox catalog contract', () => {
  it('uses the active open-sandbox catalog item rather than a UI preset id', () => {
    const sandbox = resolveOpenSandbox([
      item('smoke-test', 'quick_start'),
      item('sandbox-minimal', 'open_sandbox', 'deprecated'),
      item('ai-sandbox', 'open_sandbox'),
    ]);
    expect(sandbox?.catalog_item_id).toBe('ai-sandbox');
  });
});

