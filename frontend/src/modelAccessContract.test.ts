import { describe, expect, it } from 'vitest';
import type { AvailableModel } from './api/types';
import { defaultModelSelection, toggleModelSelection } from './modelAccessContract';

const models: AvailableModel[] = [
  { id: 'a', display_name: 'A', hardware: 'Xeon', use_case: 'Chat', status: 'healthy' },
  { id: 'b', display_name: 'B', hardware: 'Xeon', use_case: 'RAG', status: 'healthy' },
];

describe('sandbox model access contract', () => {
  it('preselects only healthy catalog defaults', () => {
    expect(defaultModelSelection({ required_models: ['a', 'stopped'] }, models)).toEqual(['a']);
  });

  it('supports selecting multiple model ids', () => {
    expect(toggleModelSelection(toggleModelSelection([], 'a'), 'b')).toEqual(['a', 'b']);
  });
});
