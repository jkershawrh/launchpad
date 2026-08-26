import type { AvailableModel } from './api/types';

export function defaultModelSelection(metadata: Record<string, unknown> | undefined, available: AvailableModel[]): string[] {
  const defaults = Array.isArray(metadata?.required_models) ? metadata.required_models : [];
  return defaults.filter(
    (model): model is string => typeof model === 'string' && available.some((item) => item.id === model)
  );
}

export function toggleModelSelection(selected: string[], modelId: string): string[] {
  return selected.includes(modelId)
    ? selected.filter((id) => id !== modelId)
    : [...selected, modelId];
}
