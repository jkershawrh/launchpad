import { describe, expect, it } from 'vitest';
import type { CatalogItem } from './api/types';
import {
  groupByLearningProgression,
  groupBySolutionFamily,
  learningLevel,
  learningStage,
  prerequisites,
  recommendedNextItems,
  solutionFamily,
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
    expect(learningStage(item('scale', '501'))).toBe('Scale');
    expect(learningLevel(item('unknown', '999'))).toBeUndefined();
  });

  it('groups catalog items by customer usage while retaining learning levels', () => {
    const agentic = item('agent', '201');
    agentic.metadata = { learning_level: '201', solution_family: 'agentic_ai' };
    const inference = item('serve', '101');
    inference.metadata = { learning_level: '101', solution_family: 'inference' };

    expect(solutionFamily(agentic)).toBe('agentic_ai');
    expect(groupBySolutionFamily([agentic, inference]).map((section) => section.family))
      .toEqual(['inference', 'agentic_ai']);
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

  it('organizes legacy deployed items by stable id when metadata is absent', () => {
    const legacy = item('intel-llm-cpu-serving');
    legacy.display_name = 'Intel AI Quickstart: Serve LLMs on Intel Xeon CPUs';
    const sections = groupByLearningProgression([legacy, item('ai-sandbox')]);

    expect(sections.map((section) => section.level)).toEqual(['001', '101']);
    expect(sections[1].items[0].catalog_item_id).toBe('intel-llm-cpu-serving');
  });
});
