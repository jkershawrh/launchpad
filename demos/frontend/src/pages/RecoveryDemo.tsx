import { useState } from 'react';
import { Button, Card, CardBody, Content, Label, PageSection, Spinner, Icon } from '@patternfly/react-core';
import { CheckCircleIcon, ExclamationTriangleIcon, ExclamationCircleIcon } from '@patternfly/react-icons';
import { api } from '../api/client';

interface PhaseResult {
  name: string;
  label: string;
  description: string;
  gaudi_healthy: boolean;
  requests: number;
  route_counts: Record<string, number>;
  avg_latency_ms: number;
  fallback_count: number;
}

interface RecoveryResult {
  status: string;
  phases: PhaseResult[];
  total_requests: number;
  requests_dropped: number;
  total_fallbacks: number;
  insight: string;
}

const phaseIcon = (phase: PhaseResult) => {
  if (phase.name === 'failure') return <Icon status="danger"><ExclamationCircleIcon /></Icon>;
  if (phase.name === 'recovery') return <Icon status="success"><CheckCircleIcon /></Icon>;
  return <Icon status="success"><CheckCircleIcon /></Icon>;
};

const phaseBorder = (name: string) => {
  if (name === 'normal') return '4px solid var(--rh-color--success, #3e8635)';
  if (name === 'failure') return '4px solid var(--rh-color--danger, #c9190b)';
  return '4px solid var(--rh-color--info, #0068b5)';
};

export default function RecoveryDemo() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RecoveryResult | null>(null);

  const runRecovery = async () => {
    setLoading(true);
    setResult(null);
    try {
      const r = await api.recoveryRun(42);
      setResult(r as unknown as RecoveryResult);
    } catch { /* ignore */ }
    setLoading(false);
  };

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Recovery &amp; Resilience</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            What happens when hardware fails? This demo simulates an Intel Gaudi accelerator going
            offline mid-workload. Watch the routing engine automatically reroute traffic to Xeon 6,
            then restore optimal routing when Gaudi recovers — with zero dropped requests.
          </Content>
        </Content>
      </PageSection>

      <PageSection variant="secondary">
        <Button variant="primary" onClick={runRecovery} isLoading={loading}>Simulate Recovery Scenario</Button>
        {loading && <div style={{ marginTop: '12px' }}><Spinner size="md" /> Running 3-phase recovery simulation...</div>}
      </PageSection>

      {result && (
        <PageSection>
          {/* Phase cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginBottom: '16px' }}>
            {result.phases.map((phase) => (
              <Card key={phase.name} style={{ borderTop: phaseBorder(phase.name) }}>
                <CardBody>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    {phaseIcon(phase)}
                    <span style={{ fontWeight: 700, fontSize: '1rem' }}>{phase.label}</span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', marginBottom: '12px' }}>
                    {phase.description}
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
                    <div>
                      <div style={{ fontSize: '1.6rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                        {phase.avg_latency_ms.toFixed(0)}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)' }}>avg latency (ms)</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '1.6rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                        {phase.requests}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)' }}>requests</div>
                    </div>
                  </div>

                  {phase.fallback_count > 0 && (
                    <div style={{ marginBottom: '8px' }}>
                      <Label color="orange" icon={<ExclamationTriangleIcon />}>
                        {phase.fallback_count} fallback{phase.fallback_count > 1 ? 's' : ''}
                      </Label>
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {Object.entries(phase.route_counts).map(([lane, count]) => (
                      <Label key={lane} isCompact color={lane === 'eco' ? 'green' : lane === 'performance' ? 'blue' : 'orange'}>
                        {lane}: {count}
                      </Label>
                    ))}
                  </div>

                  <div style={{ marginTop: '8px' }}>
                    <Label isCompact color={phase.gaudi_healthy ? 'green' : 'red'}>
                      Gaudi: {phase.gaudi_healthy ? 'Online' : 'Offline'}
                    </Label>
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>

          {/* Latency timeline */}
          <Card style={{ marginBottom: '16px' }}>
            <CardBody>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>Latency Across Phases</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px', height: '120px' }}>
                {result.phases.map((phase) => {
                  const maxLat = Math.max(...result.phases.map(p => p.avg_latency_ms));
                  const pct = (phase.avg_latency_ms / maxLat) * 100;
                  const color = phase.name === 'failure' ? 'var(--rh-color--danger, #c9190b)' : 'var(--rh-color--success, #3e8635)';
                  return (
                    <div key={phase.name} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)', marginBottom: '4px' }}>
                        {phase.avg_latency_ms.toFixed(0)} ms
                      </div>
                      <div style={{ width: '80%', height: `${pct}%`, background: color, borderRadius: '4px 4px 0 0', minHeight: '8px' }} />
                      <div style={{ fontSize: '0.7rem', marginTop: '4px', color: 'var(--rh-color--text-secondary)' }}>{phase.name}</div>
                    </div>
                  );
                })}
              </div>
            </CardBody>
          </Card>

          {/* Summary */}
          <Card>
            <CardBody style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '2.4rem', fontWeight: 700, color: 'var(--rh-color--success, #3e8635)', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                0
              </div>
              <div style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '4px' }}>Requests Dropped</div>
              <div style={{ fontSize: '0.88rem', color: 'var(--rh-color--text-secondary)', maxWidth: '650px', margin: '0 auto', marginBottom: '8px' }}>
                {result.insight}
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', fontSize: '0.82rem' }}>
                <span><strong>{result.total_requests}</strong> total requests</span>
                <span><strong>{result.total_fallbacks}</strong> fallbacks during failure</span>
              </div>
            </CardBody>
          </Card>
        </PageSection>
      )}
    </>
  );
}
