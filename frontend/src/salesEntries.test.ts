import { describe, expect, it } from 'vitest';
import { SALES_ENTRIES, salesEntryUrl } from './salesEntries';

describe('sales entries', () => {
  it('keeps five presentation-only entries mapped to the intended learning paths', () => {
    expect(SALES_ENTRIES).toHaveLength(5);
    expect(SALES_ENTRIES.find((entry) => entry.id === 'governed-agentic')?.labCatalogId).toBe('agentic-ai-101');
    expect(SALES_ENTRIES.find((entry) => entry.id === 'virtualization-ai')?.labCatalogId).toBe('virtualization-ai-foundations-101');
    expect(SALES_ENTRIES.find((entry) => entry.id === 'ai-strategy')?.labCatalogId).toBeUndefined();
  });

  it('derives story URLs only from an OpenShift application hostname', () => {
    expect(salesEntryUrl('sales-ai-strategy', 'launchpad-candidate.apps.flightpath.fm2aihpcsed.com'))
      .toBe('https://sales-ai-strategy.apps.flightpath.fm2aihpcsed.com');
    expect(salesEntryUrl('sales-ai-strategy', 'labs.smg-helix.ai')).toBeUndefined();
    expect(salesEntryUrl('sales-ai-strategy', 'localhost')).toBeUndefined();
  });
});
