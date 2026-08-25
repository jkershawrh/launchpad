import { describe, expect, it } from 'vitest';
import { scenarioKeysForDemo } from '../../pages/scenarioSelection';

describe('scenarioKeysForDemo', () => {
  it('focuses the guided RAG catalog item on the RAG workflow', () => {
    expect(scenarioKeysForDemo('guided-rag-on-xeon')).toEqual(['rag']);
  });

  it('keeps the complete showroom for the general demo', () => {
    expect(scenarioKeysForDemo('Intel x Red Hat AI Platform')).toEqual([
      'rag',
      'aiops',
      'agent',
      'custom',
    ]);
  });
});
