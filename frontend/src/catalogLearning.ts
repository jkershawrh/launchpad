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

const LEGACY_CATALOG_LEVEL: Record<string, LearningLevel> = {
  'ai-sandbox': '001',
  'smoke-test': '001',
  'cpu-inference-serving': '101',
  'intel-llm-cpu-serving': '101',
  'rag-on-xeon': '101',
  'guided-rag-on-xeon': '201',
  'hybrid-fraud-detection': '201',
  'intel-llm-tool-calling': '201',
  'intel-xeon6-agent-201': '201',
  'openshift-operators-workshop': '201',
  'agent-reliability-quickstart': '301',
  'multi-agent-quickstart': '301',
  'network-operations-agent': '301',
  'agentops-observability': '401',
};

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === 'string') : [];
}

export function learningLevel(item: CatalogItem): LearningLevel | undefined {
  const value = item.metadata?.learning_level;
  const normalized = typeof value === 'number' ? String(value).padStart(3, '0') : value;
  const declared = LEARNING_LEVELS.find((level) => level === normalized);
  if (declared) return declared;
  const titleLevel = item.display_name.match(/(?:AI\s+)?(001|101|201|301|401)\b/)?.[1];
  return LEARNING_LEVELS.find((level) => level === titleLevel)
    ?? LEGACY_CATALOG_LEVEL[item.catalog_item_id];
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

export interface CatalogLearningSection {
  level: LearningLevel | 'other';
  stage: string;
  items: CatalogItem[];
}

export function groupByLearningProgression(items: CatalogItem[]): CatalogLearningSection[] {
  const sorted = sortByLearningProgression(items);
  const sections: CatalogLearningSection[] = LEARNING_LEVELS.map((level) => ({
    level,
    stage: LEARNING_STAGE[level],
    items: sorted.filter((item) => learningLevel(item) === level),
  })).filter((section) => section.items.length > 0);
  const other = sorted.filter((item) => !learningLevel(item));
  return other.length > 0
    ? [...sections, { level: 'other', stage: 'Additional environments', items: other }]
    : sections;
}
