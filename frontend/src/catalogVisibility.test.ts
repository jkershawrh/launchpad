import { describe, expect, it } from 'vitest';
import type { CatalogItem } from './api/types';
import {
  allowedExposurePolicies,
  participantCatalog,
  resolveParticipantCatalogId,
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

  it('collapses compatibility aliases out of the participant learning catalog', () => {
    const canonical = item('intel-llm-cpu-serving', 'active');
    const alias = {
      ...item('rag-on-xeon', 'active'),
      metadata: {
        migration_mode: 'compatibility_alias',
        canonical_item_id: 'intel-llm-cpu-serving',
      },
    };

    expect(participantCatalog([canonical, alias]).map((entry) => entry.catalog_item_id)).toEqual([
      'intel-llm-cpu-serving',
    ]);
  });

  it('keeps explicitly internal diagnostics out of participant ordering even if active', () => {
    const diagnostic = {
      ...item('smoke-test', 'active'),
      metadata: {
        catalog_visibility: 'internal_diagnostic',
        participant_orderable: false,
      },
    };

    expect(participantCatalog([diagnostic])).toEqual([]);
  });

  it('resolves a compatibility alias only to its visible canonical item', () => {
    const canonical = item('intel-llm-cpu-serving', 'active');
    const alias = {
      ...item('cpu-inference-serving', 'active'),
      metadata: {
        migration_mode: 'compatibility_alias',
        canonical_item_id: 'intel-llm-cpu-serving',
      },
    };

    expect(
      resolveParticipantCatalogId([alias, canonical], 'cpu-inference-serving'),
    ).toBe('intel-llm-cpu-serving');
    expect(resolveParticipantCatalogId([alias], 'cpu-inference-serving')).toBe('');
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
