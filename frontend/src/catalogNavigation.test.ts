import { describe, expect, it } from 'vitest';
import { catalogLaunchPath } from './catalogNavigation';

describe('catalogLaunchPath', () => {
  it('opens guided builds in the request form with the catalog item selected', () => {
    expect(catalogLaunchPath('guided_build', 'guided-rag-on-xeon')).toBe(
      '/request?catalog_item=guided-rag-on-xeon',
    );
  });

  it('opens sandboxes in the sandbox configurator', () => {
    expect(catalogLaunchPath('open_sandbox', 'open-sandbox')).toBe('/sandbox');
  });

  it('keeps quick starts in the one-click demo flow', () => {
    expect(catalogLaunchPath('quick_start', 'qs-rag-chatbot')).toBe(
      '/demos?launch=qs-rag-chatbot',
    );
  });
});
