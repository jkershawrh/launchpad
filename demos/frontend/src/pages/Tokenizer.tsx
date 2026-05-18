import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardTitle,
  Content,
  Gallery,
  GalleryItem,
  Label,
  PageSection,
  Spinner,
  Switch,
  TextArea,
  Alert,
} from '@patternfly/react-core';
import { api } from '../api/client';

const MODELS = [
  { key: 'granite-4-0-h-tiny', label: 'Granite Tiny', lane: 'Eco', hw: 'Xeon 6', color: 'var(--rh-color--success)', bg: 'var(--rh-color--success-bg)', labelColor: 'green' as const },
  { key: 'codellama-7b-instruct', label: 'CodeLlama 7B', lane: 'Performance', hw: 'Xeon 6', color: 'var(--rh-color--xeon6)', bg: 'var(--rh-color--xeon6-bg)', labelColor: 'blue' as const },
  { key: 'llama-scout-17b', label: 'Llama Scout 17B', lane: 'Overdrive', hw: 'Gaudi', color: 'var(--rh-color--gaudi)', bg: 'var(--rh-color--gaudi-bg)', labelColor: 'orange' as const },
];

const THRESHOLDS = [
  { max: 4000, lane: 'Eco', hw: 'Xeon 6', color: 'var(--rh-color--success)' },
  { max: 16000, lane: 'Performance', hw: 'Xeon 6', color: 'var(--rh-color--xeon6)' },
  { max: 64000, lane: 'Overdrive', hw: 'Gaudi', color: 'var(--rh-color--gaudi)' },
];

const MAX_TEXT_LENGTH = 5000;

const PRESETS = [
  { label: 'Short', text: 'Classify this support ticket as urgent or routine.' },
  { label: 'Medium', text: 'The monitoring system detected elevated p99 latency on the inference gateway pods in the production namespace. The average response time increased from 850ms to 4,200ms over the last 15 minutes. CPU utilization on the Xeon 6 worker nodes is at 78% while Gaudi accelerator memory usage remains stable at 42%. No pod restarts or OOM events have been recorded. The issue correlates with a 3x increase in batch generation requests from the analytics pipeline.' },
  { label: 'Long', text: 'Incident Report: Production Inference Gateway Degradation\n\nSummary: At 14:23 UTC, the AI inference gateway began routing all requests to the CPU-only eco lane after the Gaudi accelerator nodes reported high memory pressure. This caused a cascade of latency increases as large language model requests (17B+ parameters) that normally run on Gaudi were forced onto Xeon 6 hardware.\n\nTimeline:\n- 14:23 UTC: Gaudi node memory utilization exceeded 95% threshold\n- 14:24 UTC: Overdrive lane health check failed, routing engine activated fallback rules\n- 14:25 UTC: Performance lane received 4x normal traffic volume\n- 14:28 UTC: p99 latency crossed 10,000ms SLA threshold\n- 14:32 UTC: On-call engineer acknowledged alert and began investigation\n- 14:45 UTC: Root cause identified — a batch summarization job consumed all available HBM\n- 14:48 UTC: Batch job terminated, Gaudi memory freed\n- 14:50 UTC: Overdrive lane restored, latency returned to baseline\n\nRoot Cause: An unthrottled batch summarization workload consumed all 96GB of HBM on the Gaudi accelerator, preventing new inference requests from being scheduled. The batch job lacked resource limits and was not subject to the admission controller\'s token budget.\n\nImpact: 27 minutes of degraded inference performance. 142 requests experienced latency above SLA. Zero requests were dropped due to graceful fallback routing.\n\nAction Items:\n1. Add resource limits to batch generation workloads\n2. Implement token budget admission controller for Gaudi lane\n3. Add HBM utilization alert at 80% threshold\n4. Review fallback routing capacity planning for sustained failover scenarios' },
];

interface ModelResult {
  token_count: number;
  tokens: string[];
  mode: string;
  cost_estimate: number;
}

const TOKEN_COLORS = [
  '#e8f5e9', '#e3f2fd', '#fff3e0', '#f3e5f5', '#e0f7fa',
  '#fce4ec', '#f1f8e9', '#e8eaf6', '#fff8e1', '#e0f2f1',
];

export default function Tokenizer() {
  const [text, setText] = useState(PRESETS[0].text);
  const [realMode, setRealMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState<Record<string, ModelResult> | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchTokens = useCallback(async (input: string, mode: 'approximate' | 'real') => {
    const cleaned = input
      .slice(0, MAX_TEXT_LENGTH)
      .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');
    if (!cleaned.trim() || cleaned.trim().length < 2) {
      setResults(null);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data = await api.tokenize(cleaned, mode) as { models: Record<string, ModelResult> };
      setResults(data.models);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tokenization failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchTokens(text, realMode ? 'real' : 'approximate');
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [text, realMode, fetchTokens]);

  const maxTokens = results
    ? Math.max(...Object.values(results).map(r => r.token_count))
    : 0;

  const activeLane = THRESHOLDS.find(t => maxTokens <= t.max) || THRESHOLDS[THRESHOLDS.length - 1];

  return (
    <>
      {/* Hero */}
      <PageSection>
        <Content>
          <Content component="h1">Tokenization & Cost Explorer</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            Text gets split into tokens — small chunks the model processes. More tokens means
            higher cost. Different models split the same text differently. Token count is the
            trigger that decides whether Intel Xeon 6 or Gaudi handles the request.
          </Content>
        </Content>
      </PageSection>

      {/* Input */}
      <PageSection variant="secondary">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          <Content component="h2" style={{ margin: 0 }}>Enter Text</Content>
          <Switch
            id="tokenizer-mode"
            label={realMode ? "Real Tokenizers" : "Approximate"}
            isChecked={realMode}
            onChange={(_e, checked) => setRealMode(checked)}
          />
          {realMode && (
            <Label color="orange" isCompact>First call may take a few seconds to load models</Label>
          )}
        </div>

        <TextArea
          value={text}
          onChange={(_e, val) => setText(val.slice(0, MAX_TEXT_LENGTH))}
          aria-label="Text to tokenize"
          rows={5}
          maxLength={MAX_TEXT_LENGTH}
          validated={text.length >= MAX_TEXT_LENGTH ? 'warning' : 'default'}
          style={{ maxWidth: '780px', fontFamily: 'var(--pf-t--global--font--family--mono)', fontSize: '0.88rem' }}
        />
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <Content component="small" style={{ fontWeight: 600, marginRight: '0.25rem' }}>Presets:</Content>
          {PRESETS.map(p => (
            <Button key={p.label} variant="secondary" size="sm" onClick={() => setText(p.text)}>
              {p.label}
            </Button>
          ))}
          <span style={{
            marginLeft: 'auto', fontSize: '0.82rem',
            color: text.length >= MAX_TEXT_LENGTH ? 'var(--rh-color--brand)' : 'var(--pf-t--global--text--color--subtle)',
          }}>
            {text.length.toLocaleString()} / {MAX_TEXT_LENGTH.toLocaleString()} characters
          </span>
        </div>
      </PageSection>

      {/* Results */}
      {error && (
        <PageSection>
          <Alert variant="danger" title={error} isInline />
        </PageSection>
      )}

      {loading && !results && (
        <PageSection>
          <Spinner size="lg" aria-label="Tokenizing" />
        </PageSection>
      )}

      {results && (
        <>
          {/* Token threshold gauge */}
          <PageSection>
            <Content component="h2" style={{ marginBottom: '0.75rem' }}>Hardware Routing Threshold</Content>
            <Content component="p" style={{ maxWidth: '640px', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
              The token count determines which Intel hardware tier handles the request.
              This gauge shows where your text falls on the routing scale.
            </Content>
            <div style={{ maxWidth: '700px' }}>
              <div style={{ display: 'flex', height: '32px', borderRadius: 6, overflow: 'hidden', marginBottom: '0.5rem' }}>
                {THRESHOLDS.map((t, i) => {
                  const prevMax = i > 0 ? THRESHOLDS[i - 1].max : 0;
                  const width = ((t.max - prevMax) / THRESHOLDS[THRESHOLDS.length - 1].max) * 100;
                  const isActive = activeLane === t;
                  return (
                    <div key={t.lane} style={{
                      width: `${width}%`, background: t.color,
                      opacity: isActive ? 1 : 0.25,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: '#fff', fontSize: '0.78rem', fontWeight: 600,
                      transition: 'opacity 0.3s',
                    }}>
                      {t.lane} ({t.hw})
                    </div>
                  );
                })}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--rh-color--text-secondary)' }}>
                <span>0</span>
                <span>4K</span>
                <span>16K</span>
                <span>64K</span>
              </div>
              <div style={{
                marginTop: '0.75rem', padding: '8px 14px', borderRadius: '6px',
                background: activeLane.color, color: '#fff', fontWeight: 600,
                display: 'inline-block', fontSize: '0.88rem',
              }}>
                {maxTokens.toLocaleString()} tokens → {activeLane.lane} lane ({activeLane.hw})
              </div>
            </div>
          </PageSection>

          {/* Side-by-side token comparison */}
          <PageSection variant="secondary">
            <Content component="h2" style={{ marginBottom: '0.75rem' }}>Token Comparison Across Models</Content>
            <Content component="p" style={{ maxWidth: '640px', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
              Each model uses a different tokenizer vocabulary. The same text produces different
              token counts — and different costs — depending on which model processes it.
            </Content>

            <Gallery hasGutter minWidths={{ default: '280px' }}>
              {MODELS.map(m => {
                const r = results[m.key];
                if (!r) return null;
                return (
                  <GalleryItem key={m.key}>
                    <Card isFullHeight style={{ borderTop: `4px solid ${m.color}` }}>
                      <CardTitle>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontWeight: 700 }}>{m.label}</span>
                          <Label isCompact color={m.labelColor}>{m.hw}</Label>
                          <Label isCompact color="grey">{m.lane}</Label>
                        </div>
                      </CardTitle>
                      <CardBody>
                        <div style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                          {r.token_count.toLocaleString()}
                        </div>
                        <div style={{ fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)', marginBottom: '1rem' }}>
                          tokens ({r.mode})
                        </div>

                        {/* Token chips */}
                        <div style={{
                          display: 'flex', flexWrap: 'wrap', gap: '3px',
                          maxHeight: '160px', overflow: 'auto',
                          padding: '8px', borderRadius: '6px',
                          background: 'var(--rh-color--surface-secondary)',
                          border: '1px solid var(--rh-color--border)',
                        }}>
                          {r.tokens.slice(0, 200).map((tok, i) => (
                            <span key={i} style={{
                              padding: '2px 5px', borderRadius: '3px',
                              fontSize: '0.72rem', fontFamily: 'var(--pf-t--global--font--family--mono)',
                              background: TOKEN_COLORS[i % TOKEN_COLORS.length],
                              border: '1px solid rgba(0,0,0,0.08)',
                              whiteSpace: 'pre',
                            }}>
                              {tok}
                            </span>
                          ))}
                          {r.tokens.length > 200 && (
                            <span style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)', padding: '2px 5px' }}>
                              +{r.tokens.length - 200} more
                            </span>
                          )}
                        </div>
                      </CardBody>
                    </Card>
                  </GalleryItem>
                );
              })}
            </Gallery>
          </PageSection>

          {/* Cost comparison */}
          <PageSection>
            <Content component="h2" style={{ marginBottom: '0.75rem' }}>Cost Comparison</Content>
            <Content component="p" style={{ maxWidth: '640px', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
              Different hardware tiers have different cost profiles. The routing engine
              automatically selects the cheapest viable option for each workload.
            </Content>

            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
              {MODELS.map(m => {
                const r = results[m.key];
                if (!r) return null;
                const maxCost = Math.max(...Object.values(results).map(v => v.cost_estimate));
                const barPct = maxCost > 0 ? (r.cost_estimate / maxCost) * 100 : 0;
                return (
                  <Card key={m.key} style={{ flex: '1 1 200px', maxWidth: '280px', borderTop: `4px solid ${m.color}` }}>
                    <CardBody>
                      <div style={{ fontWeight: 700, marginBottom: '4px' }}>{m.label}</div>
                      <Label isCompact color={m.labelColor} style={{ marginBottom: '0.5rem' }}>{m.hw}</Label>
                      <div style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.5rem' }}>
                        ${r.cost_estimate.toFixed(4)}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)' }}>
                        {r.token_count.toLocaleString()} tokens
                      </div>
                      <div style={{
                        height: '8px', borderRadius: '4px', marginTop: '0.75rem',
                        background: 'var(--rh-color--surface-secondary)',
                        overflow: 'hidden',
                      }}>
                        <div style={{
                          height: '100%', width: `${barPct}%`,
                          background: m.color, borderRadius: '4px',
                          transition: 'width 0.3s',
                        }} />
                      </div>
                    </CardBody>
                  </Card>
                );
              })}
            </div>

            {(() => {
              const xeonCost = results['granite-4-0-h-tiny']?.cost_estimate ?? 0;
              const gaudiCost = results['llama-scout-17b']?.cost_estimate ?? 0;
              const savings = gaudiCost > 0 ? ((gaudiCost - xeonCost) / gaudiCost * 100).toFixed(0) : '0';
              return (
                <Alert variant="info" isInline title="Cost insight">
                  Running this text on Xeon 6 (Eco) costs ${xeonCost.toFixed(4)} vs ${gaudiCost.toFixed(4)} on
                  Gaudi — {savings}% savings. The routing engine sends small workloads to Xeon 6 automatically,
                  reserving Gaudi for tasks that need its memory bandwidth and throughput.
                </Alert>
              );
            })()}
          </PageSection>

          {/* Enterprise scale projection */}
          <PageSection variant="secondary">
            <Content component="h2" style={{ marginBottom: '0.75rem' }}>Enterprise Scale Projection</Content>
            <Content component="p" style={{ maxWidth: '720px', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
              A single request costs fractions of a cent. At enterprise scale — thousands to millions
              of requests per day — hardware-aware routing drives significant cost savings. The table
              below projects costs for this exact text at production volumes.
            </Content>

            {(() => {
              const scales = [
                { label: '1K requests', count: 1_000 },
                { label: '10K requests', count: 10_000 },
                { label: '100K requests', count: 100_000 },
                { label: '1M requests', count: 1_000_000 },
              ];
              const eco = results['granite-4-0-h-tiny'];
              const perf = results['codellama-7b-instruct'];
              const gaudi = results['llama-scout-17b'];
              if (!eco || !perf || !gaudi) return null;

              const fmt = (v: number) => v < 1 ? `$${v.toFixed(2)}` : v < 1000 ? `$${v.toFixed(0)}` : `$${(v / 1000).toFixed(1)}K`;

              return (
                <>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{
                      width: '100%', maxWidth: '800px', borderCollapse: 'collapse',
                      fontSize: '0.88rem',
                    }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid var(--rh-color--border-strong)' }}>
                          <th style={{ textAlign: 'left', padding: '10px 12px', fontWeight: 700 }}>Volume</th>
                          <th style={{ textAlign: 'right', padding: '10px 12px', fontWeight: 700, color: 'var(--rh-color--success)' }}>
                            Xeon 6 (Eco)
                          </th>
                          <th style={{ textAlign: 'right', padding: '10px 12px', fontWeight: 700, color: 'var(--rh-color--xeon6)' }}>
                            Xeon 6 (Perf)
                          </th>
                          <th style={{ textAlign: 'right', padding: '10px 12px', fontWeight: 700, color: 'var(--rh-color--gaudi)' }}>
                            Gaudi
                          </th>
                          <th style={{ textAlign: 'right', padding: '10px 12px', fontWeight: 700 }}>
                            Smart Routing Savings
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {scales.map(s => {
                          const ecoCost = eco.cost_estimate * s.count;
                          const perfCost = perf.cost_estimate * s.count;
                          const gaudiCost = gaudi.cost_estimate * s.count;
                          const allGaudiCost = gaudiCost;
                          const smartCost = ecoCost;
                          const saved = allGaudiCost - smartCost;
                          const savedPct = allGaudiCost > 0 ? (saved / allGaudiCost * 100).toFixed(0) : '0';
                          return (
                            <tr key={s.label} style={{ borderBottom: '1px solid var(--rh-color--border)' }}>
                              <td style={{ padding: '10px 12px', fontWeight: 600 }}>{s.label}</td>
                              <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                                {fmt(ecoCost)}
                              </td>
                              <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                                {fmt(perfCost)}
                              </td>
                              <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                                {fmt(gaudiCost)}
                              </td>
                              <td style={{
                                padding: '10px 12px', textAlign: 'right', fontWeight: 700,
                                color: 'var(--rh-color--success)',
                              }}>
                                {fmt(saved)} saved ({savedPct}%)
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <Alert variant="success" isInline style={{ marginTop: '1rem', maxWidth: '800px' }} title="Why smart routing matters at scale">
                    If every request ran on Gaudi regardless of complexity, {scales[3].label.toLowerCase()} of
                    this text would cost {fmt(gaudi.cost_estimate * 1_000_000)}. With intelligent routing sending
                    small workloads to Xeon 6, the same volume costs {fmt(eco.cost_estimate * 1_000_000)} — saving{' '}
                    {fmt((gaudi.cost_estimate - eco.cost_estimate) * 1_000_000)} per million requests. Gaudi is
                    reserved for workloads that actually need its memory bandwidth and throughput.
                  </Alert>
                </>
              );
            })()}
          </PageSection>
        </>
      )}
    </>
  );
}
