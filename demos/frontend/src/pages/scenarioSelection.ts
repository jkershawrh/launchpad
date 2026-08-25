const ALL_SCENARIO_KEYS = ['rag', 'aiops', 'agent', 'custom'] as const;

export function scenarioKeysForDemo(demoName: string): string[] {
  if (demoName === 'guided-rag-on-xeon') {
    return ['rag'];
  }

  return [...ALL_SCENARIO_KEYS];
}
