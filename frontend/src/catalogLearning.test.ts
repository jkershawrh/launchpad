import { describe, expect, it } from 'vitest';
import type { CatalogItem } from './api/types';
import {
  learningLevel,
  learningStage,
  prerequisites,
  recommendedNextItems,
  sortByLearningProgression,
} from './catalogLearning';

const item = (id: string, level?: string): CatalogItem => ({
  catalog_item_id: id,
  display_name: id,
  description: id,
  category: 'guided_build',
  version: '1.0.0',
  status: 'active',
  required_capabilities: [],
  optional_capabilities: [],
  metadata: level ? { learning_level: level } : {},
});

describe('catalog learning progression', () => {
  it('normalizes and labels supported levels', () => {
    expect(learningLevel(item('intro', '001'))).toBe('001');
    expect(learningStage(item('advanced', '301'))).toBe('Engineer');
    expect(learningLevel(item('unknown', '999'))).toBeUndefined();
  });

  it('returns safe prerequisite and recommendation lists', () => {
    const catalog = item('agent', '201');
    catalog.metadata = {
      learning_level: '201',
      prerequisites: ['serve'],
      recommended_next_items: ['reliability', 42],
    };
    expect(prerequisites(catalog)).toEqual(['serve']);
    expect(recommendedNextItems(catalog)).toEqual(['reliability']);
  });

  it('sorts by progression without mutating the API response', () => {
    const source = [item('operate', '401'), item('learn', '101'), item('unclassified')];
    expect(sortByLearningProgression(source).map((entry) => entry.catalog_item_id)).toEqual([
      'learn',
      'operate',
      'unclassified',
    ]);
    expect(source[0].catalog_item_id).toBe('operate');
  });
});
