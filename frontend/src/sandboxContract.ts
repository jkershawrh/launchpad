import type { CatalogItem } from './api/types';

export function resolveOpenSandbox(catalog: CatalogItem[]): CatalogItem | undefined {
  return catalog.find((item) => item.category === 'open_sandbox' && item.status === 'active');
}

