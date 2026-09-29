import { describe, expect, it } from 'vitest';
import type { CatalogItem } from './api/types';
import {
  allowedExposurePolicies,
  participantCatalog,
  supportsExposurePolicy,
} from './catalogVisibility';


const item = (catalog_item_id: string, status: CatalogItem['status']): CatalogItem => ({
  catalog_item_id,
  display_name: catalog_item_id,
  description: catalog_item_id,
  category: 'guided_build',
  version: '1.0.0',
  status,
  required_capabilities: [],
  optional_capabilities: [],
  metadata: {},
});


describe('participant catalog visibility', () => {
  it('shows only active catalog items in participant ordering surfaces', () => {
    const items = [
      item('ready', 'active'),
      item('importing', 'draft'),
      item('retired', 'deprecated'),
    ];

    expect(participantCatalog(items).map((entry) => entry.catalog_item_id)).toEqual([
      'ready',
    ]);
  });

  it('preserves an internal-only certification gate in ordering surfaces', () => {
    const internallyCertified = {
      ...item('virtualization-ai-201', 'active'),
      metadata: { allowed_exposure_policies: ['internal'] },
    };

    expect(allowedExposurePolicies(internallyCertified)).toEqual(['internal']);
    expect(supportsExposurePolicy(internallyCertified, 'internal')).toBe(true);
    expect(supportsExposurePolicy(internallyCertified, 'public_code')).toBe(false);
  });

  it('keeps compatibility for active catalog items without an exposure declaration', () => {
    expect(allowedExposurePolicies(item('legacy', 'active'))).toEqual([
      'internal',
      'public_code',
    ]);
  });

  it('fails closed when an exposure declaration contains no supported policy', () => {
    const invalid = {
      ...item('invalid', 'active'),
      metadata: { allowed_exposure_policies: ['unknown'] },
    };

    expect(allowedExposurePolicies(invalid)).toEqual(['internal']);
  });
});
