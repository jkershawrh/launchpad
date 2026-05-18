import { useState } from 'react';
import { Button, Card, CardBody, Content, Label, PageSection, Spinner } from '@patternfly/react-core';
import { api } from '../api/client';

interface ComparisonResult {
  run_a: { label: string; description: string; p95_latency_ms: number; requests_per_second: number; route_counts: Record<string, number>; total_duration_ms: number };
  run_b: { label: string; description: string; p95_latency_ms: number; requests_per_second: number; route_counts: Record<string, number>; total_duration_ms: number };
  speedup: number;
  insight: string;
  request_count: number;
}

export default function ReplayDemo() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ComparisonResult | null>(null);

  const runComparison = async () => {
    setLoading(true); setResult(null);
    try {
      const r = await api.replayCompare('incident_storm', 42);
      setResult(r as unknown as ComparisonResult);
    } catch { /* ignore */ }
    setLoading(false);
  };

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Replay Comparison</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            What if you ran the same workload with different hardware? This demo replays the same
            25 requests twice: once on Xeon 6 only (no GPU), once with intelligent routing across
            Xeon 6 + Gaudi. See the difference hardware-aware routing makes.
          </Content>
        </Content>
      </PageSection>

      <PageSection variant="secondary">
        <Button variant="primary" onClick={runComparison} isLoading={loading}>Run Comparison</Button>
        {loading && <div style={{ marginTop: '12px' }}><Spinner size="md" /> Simulating both hardware configurations...</div>}
      </PageSection>

      {result && (
        <PageSection>
          {/* Side by side */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
            {[result.run_a, result.run_b].map((run, i) => (
              <Card key={i} style={{ borderTop: `4px solid ${i === 0 ? 'var(--rh-color--brand)' : 'var(--rh-color--success)'}` }}>
                <CardBody>
                  <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '4px' }}>{run.label}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', marginBottom: '12px' }}>{run.description}</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    <div>
                      <div style={{ fontSize: '1.8rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)' }}>{run.p95_latency_ms.toFixed(0)}</div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)' }}>p95 latency (ms)</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '1.8rem', fontWeight: 700, fontFamily: 'var(--pf-t--global--font--family--mono)' }}>{run.requests_per_second.toFixed(1)}</div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)' }}>req/s</div>
                    </div>
                  </div>
                  <div style={{ marginTop: '8px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {Object.entries(run.route_counts).map(([lane, count]) => (
                      <Label key={lane} isCompact color={lane === 'eco' ? 'green' : lane === 'performance' ? 'blue' : 'orange'}>{lane}: {count}</Label>
                    ))}
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>

          {/* Speedup */}
          <Card style={{ marginBottom: '16px' }}>
            <CardBody style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '3rem', fontWeight: 700, color: 'var(--rh-color--success)', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                {result.speedup}x
              </div>
              <div style={{ fontSize: '0.88rem', fontWeight: 600, marginBottom: '8px' }}>faster with Intel Gaudi</div>
              <div style={{ fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)', maxWidth: '600px', margin: '0 auto' }}>
                {result.insight}
              </div>
            </CardBody>
          </Card>

          {/* Latency comparison bar */}
          <Card>
            <CardBody>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: '10px' }}>p95 Latency Comparison</div>
              {[result.run_a, result.run_b].map((run, i) => (
                <div key={i} style={{ marginBottom: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '2px' }}>
                    <span>{run.label}</span>
                    <span style={{ fontFamily: 'var(--pf-t--global--font--family--mono)', fontWeight: 700 }}>{run.p95_latency_ms.toFixed(0)} ms</span>
                  </div>
                  <div style={{ height: '12px', borderRadius: '6px', background: 'var(--rh-color--surface-secondary)', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', borderRadius: '6px',
                      width: `${(run.p95_latency_ms / Math.max(result.run_a.p95_latency_ms, result.run_b.p95_latency_ms)) * 100}%`,
                      background: i === 0 ? 'var(--rh-color--brand)' : 'var(--rh-color--success)',
                    }} />
                  </div>
                </div>
              ))}
            </CardBody>
          </Card>
        </PageSection>
      )}
    </>
  );
}
