export interface SalesEntry {
  id: string;
  title: string;
  description: string;
  routeName: string;
  labCatalogId?: string;
  labLabel: string;
}

export const SALES_ENTRIES: SalesEntry[] = [
  {
    id: 'ai-strategy',
    title: 'Red Hat × Intel AI Strategy — Choose the Path to Production',
    description: 'Start with the customer outcome, then choose the learning path that best fits the opportunity.',
    routeName: 'sales-ai-strategy',
    labLabel: 'Choose a learning path',
  },
  {
    id: 'intel-xeon',
    title: 'AI on Intel Xeon — Start Where the Workload Fits',
    description: 'Position CPU inference using workload fit, measurable evidence, and a clear next technical step.',
    routeName: 'sales-intel-xeon',
    labCatalogId: 'intel-llm-cpu-serving',
    labLabel: 'Continue to Serve LLMs',
  },
  {
    id: 'governed-agentic',
    title: 'Governed Agentic AI — Earn Trust Before Authority',
    description: 'Frame the authority boundary before moving into the certified agentic learning journey.',
    routeName: 'sales-governed-agentic',
    labCatalogId: 'agentic-ai-101',
    labLabel: 'Continue to Agentic AI 101',
  },
  {
    id: 'sovereign-ai',
    title: 'Sovereign AI — Control What You Can Prove',
    description: 'Connect sovereignty requirements to enforceable controls and an evidence-backed lab pathway.',
    routeName: 'sales-sovereign-ai',
    labCatalogId: 'sovereign-ai-101',
    labLabel: 'Continue to Sovereign AI 101',
  },
  {
    id: 'virtualization-ai',
    title: 'Virtualization + AI — Modernize Without Waiting',
    description: 'Show how existing virtualized estates can become a practical entry point for governed AI.',
    routeName: 'sales-virtualization-ai',
    labCatalogId: 'virtualization-ai-foundations-101',
    labLabel: 'Continue to Virtualization + AI 101',
  },
];

export function salesEntryUrl(routeName: string, hostname: string): string | undefined {
  const match = hostname.toLowerCase().match(/^[a-z0-9-]+\.(apps\.[a-z0-9.-]+)$/);
  if (!match) return undefined;
  return `https://${routeName}.${match[1]}`;
}
