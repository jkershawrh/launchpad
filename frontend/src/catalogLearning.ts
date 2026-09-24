import type { CatalogItem } from './api/types';

export const LEARNING_LEVELS = ['001', '101', '201', '301', '401'] as const;
export type LearningLevel = typeof LEARNING_LEVELS[number];

export const LEARNING_STAGE: Record<LearningLevel, string> = {
  '001': 'Explore',
  '101': 'Learn',
  '201': 'Build',
  '301': 'Engineer',
  '401': 'Operate',
};

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === 'string') : [];
}

export function learningLevel(item: CatalogItem): LearningLevel | undefined {
  const value = item.metadata?.learning_level;
  const normalized = typeof value === 'number' ? String(value).padStart(3, '0') : value;
  return LEARNING_LEVELS.find((level) => level === normalized);
}

export function learningStage(item: CatalogItem): string | undefined {
  const level = learningLevel(item);
  return level ? LEARNING_STAGE[level] : undefined;
}

export function prerequisites(item: CatalogItem): string[] {
  return stringList(item.metadata?.prerequisites);
}

export function recommendedNextItems(item: CatalogItem): string[] {
  return stringList(item.metadata?.recommended_next_items);
}

export function sortByLearningProgression(items: CatalogItem[]): CatalogItem[] {
  return [...items].sort((left, right) => {
    const leftLevel = learningLevel(left) ?? '999';
    const rightLevel = learningLevel(right) ?? '999';
    return leftLevel.localeCompare(rightLevel) || left.display_name.localeCompare(right.display_name);
  });
}
