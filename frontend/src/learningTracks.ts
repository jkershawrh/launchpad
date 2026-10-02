import type { LearningLevel } from './catalogLearning';

export type TrackLifecycle = 'active' | 'draft' | 'planned';

export interface LearningTrackEntry {
  level: LearningLevel;
  title: string;
  lifecycle: TrackLifecycle;
  catalogId?: string;
}

export interface LearningTrack {
  id: 'agentic_ai' | 'sovereign_ai' | 'virtualization_ai';
  label: string;
  description: string;
  entries: LearningTrackEntry[];
}

export const LEARNING_TRACKS: LearningTrack[] = [
  {
    id: 'agentic_ai',
    label: 'Agentic AI',
    description: 'Progress from agentic workflow concepts to governed, evidence-backed authority.',
    entries: [
      { level: '101', title: 'Understand Agentic Workflows', lifecycle: 'draft' },
      { level: '201', title: 'Build an AI Agent on Intel Xeon 6', lifecycle: 'active', catalogId: 'intel-xeon6-agent-201' },
      { level: '301', title: 'Build Multi-Agent Systems', lifecycle: 'active', catalogId: 'multi-agent-quickstart' },
      { level: '401', title: 'Operate Evidence-Backed Agents', lifecycle: 'active', catalogId: 'operate-agentic-blueprint' },
      { level: '501', title: 'Scale and Certify Agentic Systems', lifecycle: 'active', catalogId: 'scale-agentic-blueprint' },
      { level: '601', title: 'Earn the Right to Act', lifecycle: 'active', catalogId: 'agentic-ai-601' },
    ],
  },
  {
    id: 'sovereign_ai',
    label: 'Sovereign AI',
    description: 'Build, govern, protect, and certify sovereign AI workloads and their data boundaries.',
    entries: [
      { level: '101', title: 'Understand Sovereign AI', lifecycle: 'active', catalogId: 'sovereign-ai-101' },
      { level: '201', title: 'Build a Governed Sovereign Workload', lifecycle: 'active', catalogId: 'sovereign-ai-201' },
      { level: '301', title: 'Govern Models, Data, and Agents', lifecycle: 'active', catalogId: 'sovereign-ai-301' },
      { level: '401', title: 'Confidential AI with Intel TDX', lifecycle: 'active', catalogId: 'sovereign-ai-401' },
      { level: '501', title: 'Prove and Certify Sovereign AI', lifecycle: 'active', catalogId: 'sovereign-ai-501' },
    ],
  },
  {
    id: 'virtualization_ai',
    label: 'Virtualization + AI',
    description: 'Connect existing virtualized estates to AI and modernize them through governed operations.',
    entries: [
      { level: '101', title: 'Understand VM and AI Coexistence', lifecycle: 'active', catalogId: 'virtualization-ai-foundations-101' },
      { level: '201', title: 'Connect a VM to AI', lifecycle: 'active', catalogId: 'virtualization-ai-201' },
      { level: '301', title: 'Modernize VMs with AI', lifecycle: 'active', catalogId: 'virtualization-ai-301' },
      { level: '401', title: 'Operate Hybrid VM and AI Workloads', lifecycle: 'active', catalogId: 'virtualization-ai-401' },
      { level: '501', title: 'Scale Governed AI Modernization', lifecycle: 'active', catalogId: 'virtualization-ai-501' },
    ],
  },
];
