import { Label } from '@patternfly/react-core';
import type { Accelerator } from '../api/types';
import { hwColors } from '../constants/hwColors';

interface Step {
  label: string;
  hw: Accelerator;
  detail: string;
}

interface Workflow {
  title: string;
  subtitle: string;
  steps: Step[];
}

const workflows: Workflow[] = [
  {
    title: 'Enterprise RAG',
    subtitle: 'Embed → Search → Rerank → Generate',
    steps: [
      { label: 'Embed Query', hw: 'xeon6', detail: 'nomic-embed · AMX · <500ms' },
      { label: 'Vector Search', hw: 'xeon6', detail: 'Embeddings similarity · <1s' },
      { label: 'Rerank Candidates', hw: 'xeon6', detail: 'Cross-encoder · <1s' },
      { label: 'Generate Answer', hw: 'gaudi', detail: 'llama-scout-17b · <1s' },
    ],
  },
  {
    title: 'AIOps Copilot',
    subtitle: 'Classify → Correlate → Analyze → Validate',
    steps: [
      { label: 'Classify Severity', hw: 'xeon6', detail: 'granite-tiny · <1s' },
      { label: 'Find Similar Incidents', hw: 'xeon6', detail: 'nomic-embed · <500ms' },
      { label: 'Generate RCA', hw: 'gaudi', detail: 'llama-scout-17b · <1s' },
      { label: 'Governance Gate', hw: 'xeon6', detail: 'granite-tiny · risk eval' },
    ],
  },
  {
    title: 'Governed Agent',
    subtitle: 'Intent → Risk → Plan → Policy',
    steps: [
      { label: 'Classify Intent', hw: 'xeon6', detail: 'granite-tiny · <1s' },
      { label: 'Score Risk', hw: 'xeon6', detail: 'granite-tiny · risk scoring' },
      { label: 'Generate Plan', hw: 'gaudi', detail: 'llama-scout-17b · <1s' },
      { label: 'Policy Check', hw: 'xeon6', detail: 'granite-tiny · pass / fail' },
    ],
  },
];

/* hwColors imported from ../constants/hwColors */
const hwLabels: Record<string, string> = {
  xeon6: 'Xeon 6',
  gaudi: 'Gaudi',
  local: 'Local',
};

export default function WorkflowDiagrams() {
  return (
    <div role="img" aria-label="Three workflow diagrams showing how Enterprise RAG, AIOps Copilot, and Governed Agent route multi-step inference across Xeon 6 CPU and Gaudi GPU hardware" style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', justifyContent: 'center' }}>
      {workflows.map((wf) => (
        <div key={wf.title} style={{
          flex: '1 1 280px', maxWidth: '340px',
          border: '1px solid var(--pf-t--global--border--color--default)',
          borderRadius: '12px', overflow: 'hidden',
          background: 'var(--rh-color--surface)',
        }}>
          {/* Header */}
          <div style={{
            padding: '16px 20px', borderBottom: '1px solid var(--pf-t--global--border--color--default)',
            background: 'var(--pf-t--global--background--color--primary--default)',
          }}>
            <div style={{ fontWeight: 700, fontSize: '1rem' }}>{wf.title}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--pf-t--global--text--color--subtle)', marginTop: '2px' }}>
              {wf.subtitle}
            </div>
          </div>

          {/* Steps */}
          <div style={{ padding: '12px 20px' }}>
            {wf.steps.map((step, i) => {
              const hw = hwColors[step.hw];
              return (
                <div key={i}>
                  {/* Step node */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: '12px',
                    padding: '10px 14px', borderRadius: '8px',
                    background: hw.bg, border: `1.5px solid ${hw.color}`,
                  }}>
                    {/* Step number */}
                    <div style={{
                      width: '26px', height: '26px', borderRadius: '50%',
                      background: hw.color, color: 'var(--rh-color--text-on-dark)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '0.75rem', fontWeight: 700, flexShrink: 0,
                    }}>
                      {i + 1}
                    </div>
                    {/* Content */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{step.label}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--pf-t--global--text--color--subtle)' }}>
                        {step.detail}
                      </div>
                    </div>
                    {/* Badge */}
                    <Label color={hw.labelColor} isCompact style={{ flexShrink: 0 }}>
                      {hwLabels[step.hw] || step.hw}
                    </Label>
                  </div>
                  {/* Connector */}
                  {i < wf.steps.length - 1 && (
                    <div style={{
                      width: '2px', height: '16px', margin: '0 auto',
                      background: i < wf.steps.length - 1 && wf.steps[i + 1].hw !== step.hw
                        ? `linear-gradient(${hwColors[step.hw].color}, ${hwColors[wf.steps[i + 1].hw].color})`
                        : 'var(--pf-t--global--border--color--default)',
                    }} />
                  )}
                </div>
              );
            })}
          </div>

          {/* Footer summary */}
          <div style={{
            padding: '10px 20px', borderTop: '1px solid var(--pf-t--global--border--color--default)',
            background: 'var(--pf-t--global--background--color--secondary--default)',
            fontSize: '0.78rem', color: 'var(--pf-t--global--text--color--subtle)',
            textAlign: 'center',
          }}>
            {wf.steps.filter(s => s.hw === 'xeon6').length} steps on Xeon 6 &middot;{' '}
            {wf.steps.filter(s => s.hw === 'gaudi').length} on Gaudi &middot;{' '}
            {wf.steps.filter(s => s.hw === 'local').length > 0
              ? `${wf.steps.filter(s => s.hw === 'local').length} local`
              : ''}
          </div>
        </div>
      ))}
    </div>
  );
}
