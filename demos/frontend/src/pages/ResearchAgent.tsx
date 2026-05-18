import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Alert,
  Button,
  Card,
  CardBody,
  Content,
  Label,
  MenuToggle,
  PageSection,
  Select,
  SelectOption,
  Switch,
  TextArea,
} from '@patternfly/react-core';
import { CheckCircleIcon, ExclamationCircleIcon, InProgressIcon, LockIcon, PendingIcon } from '@patternfly/react-icons';
import { api } from '../api/client';

const PRESETS = [
  { label: 'Hardware Routing', question: 'How does the routing engine decide between Xeon 6 and Gaudi for different workload types?' },
  { label: 'Failover', question: 'What happens when the Gaudi accelerator goes offline? Describe the failover mechanism.' },
  { label: 'Cost & Throughput', question: 'Compare the throughput and cost characteristics of running inference on Xeon 6 vs Gaudi.' },
  { label: 'Tokenization', question: 'Explain the tokenization differences across models and how they affect routing decisions.' },
  { label: 'Governance', question: 'What governance controls are in place for AI-generated actions on this platform?' },
];

const GOVERNANCE_MODES = [
  { value: 'open', label: 'Open', desc: 'All steps auto-execute — see the full pipeline at speed' },
  { value: 'supervised', label: 'Supervised', desc: 'Auto-execute retrieval, require approval for synthesis' },
  { value: 'locked', label: 'Locked', desc: 'Every step requires explicit approval — full control' },
];

const STEP_META: Record<string, { label: string; icon: string; hwColor: string }> = {
  decompose: { label: 'Decompose Question', icon: 'D', hwColor: 'var(--rh-color--gaudi)' },
  search: { label: 'Search Knowledge Base', icon: 'S', hwColor: 'var(--rh-color--xeon6)' },
  rerank: { label: 'Rerank Documents', icon: 'R', hwColor: 'var(--rh-color--xeon6)' },
  synthesize: { label: 'Synthesize Answer', icon: 'A', hwColor: 'var(--rh-color--gaudi)' },
  governance: { label: 'Content Review', icon: 'G', hwColor: 'var(--rh-color--xeon6)' },
};

interface AgentStep {
  name: string;
  status: string;
  output: Record<string, unknown>;
  hw: string;
  routing_reason: string;
  latency_ms?: number;
}

const StatusIcon = ({ status }: { status: string }) => {
  if (status === 'done' || status === 'approved') return <CheckCircleIcon color="var(--rh-color--success)" />;
  if (status === 'running') return <InProgressIcon color="var(--rh-color--xeon6)" className="pf-v6-u-spin" />;
  if (status === 'awaiting_approval') return <LockIcon color="var(--rh-color--gaudi)" />;
  if (status === 'error') return <ExclamationCircleIcon color="var(--rh-color--brand)" />;
  return <PendingIcon color="var(--rh-color--text-secondary)" />;
};

export default function ResearchAgent() {
  const [question, setQuestion] = useState(PRESETS[0].question);
  const [govMode, setGovMode] = useState('open');
  const [liveMode, setLiveMode] = useState(false);
  const [govOpen, setGovOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [runId, setRunId] = useState<string | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [finalAnswer, setFinalAnswer] = useState<string | null>(null);
  const [citations, setCitations] = useState<Array<{ id: string; title: string; relevance: number }>>([]);
  const [expandedStep, setExpandedStep] = useState<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const runAgent = useCallback(async () => {
    setLoading(true);
    setError('');
    setSteps([]);
    setFinalAnswer(null);
    setCitations([]);
    setExpandedStep(null);
    stopPolling();

    try {
      const resp = await api.agentResearch(question, govMode, liveMode) as { run_id: string };
      setRunId(resp.run_id);

      pollRef.current = setInterval(async () => {
        try {
          const status = await api.agentStatus(resp.run_id) as Record<string, unknown>;
          setSteps((status.steps as AgentStep[]) || []);
          if (status.status === 'complete') {
            setFinalAnswer((status.answer as string) || null);
            setCitations((status.citations as Array<{ id: string; title: string; relevance: number }>) || []);
            setLoading(false);
            stopPolling();
          }
          if (status.status === 'error') {
            setError((status.error as string) || 'Agent failed');
            setLoading(false);
            stopPolling();
          }
        } catch { /* retry */ }
      }, 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start agent');
      setLoading(false);
    }
  }, [question, govMode, stopPolling]);

  const approveStep = useCallback(async (stepName: string) => {
    if (!runId) return;
    await api.agentApprove(runId, stepName);
  }, [runId]);

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">RAG Research Agent</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            Ask complex questions. Watch the agent break them down, search the knowledge base,
            rerank results, and synthesize answers. Fast steps (search, rerank) run on Intel
            Xeon 6. Heavy steps (decompose, synthesize) run on Gaudi. Every decision is
            transparent — you see what happened, why, and on which hardware.
          </Content>
        </Content>
      </PageSection>

      {/* Input */}
      <PageSection variant="secondary">
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: '1rem' }}>
          <div style={{ flex: 1, minWidth: '300px' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Question</div>
            <TextArea
              value={question}
              onChange={(_e, val) => setQuestion(val.slice(0, 500))}
              rows={2}
              maxLength={500}
              validated={question.length >= 500 ? 'warning' : question.trim().length < 5 ? 'error' : 'default'}
              style={{ fontFamily: 'var(--pf-t--global--font--family--mono)', fontSize: '0.88rem' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', fontSize: '0.75rem' }}>
              <span style={{ color: question.trim().length < 5 ? 'var(--rh-color--brand)' : 'var(--rh-color--text-secondary)' }}>
                {question.trim().length < 5 ? 'Minimum 5 characters' : ''}
              </span>
              <span style={{ color: question.length >= 500 ? 'var(--rh-color--brand)' : 'var(--rh-color--text-secondary)' }}>
                {question.length} / 500
              </span>
            </div>
          </div>
          <div style={{ minWidth: '200px' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Governance Mode</div>
            <Select
              toggle={(ref) => (
                <MenuToggle ref={ref} onClick={() => setGovOpen(!govOpen)} isExpanded={govOpen} style={{ width: '200px' }}>
                  {GOVERNANCE_MODES.find(m => m.value === govMode)?.label || govMode}
                </MenuToggle>
              )}
              isOpen={govOpen}
              onSelect={(_e, val) => { setGovMode(val as string); setGovOpen(false); }}
              onOpenChange={setGovOpen}
              selected={govMode}
            >
              {GOVERNANCE_MODES.map(m => (
                <SelectOption key={m.value} value={m.value} description={m.desc}>{m.label}</SelectOption>
              ))}
            </Select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <Button variant="primary" onClick={runAgent} isLoading={loading} isDisabled={loading || question.trim().length < 5}>
              {liveMode ? 'Run Live Agent' : 'Run Agent'}
            </Button>
            <Switch
              id="agent-live-toggle"
              label={liveMode ? 'Live Mode' : 'Simulated'}
              isChecked={liveMode}
              onChange={(_e, checked) => setLiveMode(checked)}
            />
            {liveMode && <Label color="orange" isCompact>Real LLM calls via LiteLLM — ~10-15 seconds</Label>}
          </div>
        </div>

        <Content component="small" style={{ fontWeight: 600, display: 'block', marginBottom: '8px' }}>Preset Questions:</Content>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '8px' }}>
          {PRESETS.map((p, i) => (
            <div key={i}
              onClick={() => setQuestion(p.question)}
              style={{
                padding: '10px 14px', borderRadius: '6px', cursor: 'pointer',
                background: question === p.question ? 'var(--rh-color--xeon6-bg)' : 'var(--rh-color--surface)',
                border: `1px solid ${question === p.question ? 'var(--rh-color--xeon6)' : 'var(--rh-color--border)'}`,
                transition: 'all 0.15s',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: '0.82rem', marginBottom: '4px' }}>{p.label}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--rh-color--text-secondary)', lineHeight: '1.4' }}>
                {p.question}
              </div>
            </div>
          ))}
        </div>
      </PageSection>

      {error && <PageSection><Alert variant="danger" title={error} isInline /></PageSection>}

      {/* Agent execution timeline */}
      {steps.length > 0 && (
        <PageSection>
          <Content component="h2" style={{ marginBottom: '1rem' }}>Agent Execution</Content>

          <div style={{ maxWidth: '800px' }}>
            {steps.map((step, i) => {
              const meta = STEP_META[step.name] || { label: step.name, icon: '?', hwColor: 'grey' };
              const isExpanded = expandedStep === i;

              return (
                <div key={i} style={{ display: 'flex', gap: '12px', marginBottom: '0' }}>
                  {/* Timeline line */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '36px', flexShrink: 0 }}>
                    <div style={{
                      width: '36px', height: '36px', borderRadius: '50%',
                      background: step.status === 'done' ? 'var(--rh-color--success)' :
                        step.status === 'awaiting_approval' ? 'var(--rh-color--gaudi)' :
                        step.status === 'running' ? 'var(--rh-color--xeon6)' : 'var(--rh-color--border)',
                      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '0.85rem', fontWeight: 700,
                    }}>
                      {meta.icon}
                    </div>
                    {i < steps.length - 1 && (
                      <div style={{ width: '2px', flexGrow: 1, minHeight: '16px', background: 'var(--rh-color--border)' }} />
                    )}
                  </div>

                  {/* Step content */}
                  <div style={{
                    flex: 1, paddingBottom: '16px', cursor: 'pointer',
                  }} onClick={() => setExpandedStep(isExpanded ? null : i)}>
                    {/* Header */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.92rem' }}>{meta.label}</span>
                      <Label isCompact color={step.hw === 'Gaudi' ? 'orange' : step.hw === 'Xeon 6' ? 'blue' : 'grey'}>{step.hw}</Label>
                      <StatusIcon status={step.status} />
                      {step.latency_ms != null && step.latency_ms > 0 && (
                        <span style={{ fontSize: '0.78rem', fontFamily: 'var(--pf-t--global--font--family--mono)', color: 'var(--rh-color--text-secondary)' }}>
                          {step.latency_ms.toFixed(0)}ms
                        </span>
                      )}
                    </div>

                    {/* Routing reason */}
                    <div style={{ fontSize: '0.8rem', color: 'var(--rh-color--text-secondary)', marginBottom: '6px' }}>
                      {step.routing_reason}
                    </div>

                    {/* Approval button */}
                    {step.status === 'awaiting_approval' && (
                      <Button variant="primary" size="sm" onClick={(e) => { e.stopPropagation(); approveStep(step.name); }}
                        style={{ marginBottom: '8px' }}>
                        Approve & Continue
                      </Button>
                    )}

                    {/* Expanded output */}
                    {isExpanded && step.output && (
                      <Card style={{ marginTop: '8px' }}>
                        <CardBody style={{ fontSize: '0.82rem' }}>
                          {step.name === 'decompose' && (
                            <>
                              <div style={{ fontWeight: 600, marginBottom: '6px' }}>Generated Sub-Queries:</div>
                              {((step.output.sub_queries as string[]) || []).map((sq, j) => (
                                <div key={j} style={{
                                  padding: '6px 10px', marginBottom: '4px', borderRadius: '4px',
                                  background: 'var(--rh-color--gaudi-bg)', border: '1px solid var(--rh-color--gaudi)',
                                }}>
                                  {j + 1}. {sq}
                                </div>
                              ))}
                            </>
                          )}

                          {step.name === 'search' && (
                            <>
                              <div style={{ fontWeight: 600, marginBottom: '6px' }}>
                                Retrieved {(step.output.count as number) || 0} documents for: <em>{step.output.query as string}</em>
                              </div>
                              {((step.output.documents as Array<Record<string, unknown>>) || []).map((doc, j) => (
                                <div key={j} style={{
                                  padding: '8px 10px', marginBottom: '4px', borderRadius: '4px',
                                  background: 'var(--rh-color--xeon6-bg)', border: '1px solid var(--rh-color--xeon6)',
                                }}>
                                  <div style={{ fontWeight: 600 }}>{doc.title as string}</div>
                                  <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', marginTop: '2px' }}>
                                    {(doc.content as string)?.slice(0, 150)}...
                                  </div>
                                  <Label isCompact color="blue" style={{ marginTop: '4px' }}>
                                    Score: {(doc.score as number)?.toFixed(3)}
                                  </Label>
                                </div>
                              ))}
                            </>
                          )}

                          {step.name === 'rerank' && (
                            <>
                              <div style={{ fontWeight: 600, marginBottom: '6px' }}>
                                {(step.output.count as number) || 0} documents ranked by relevance
                              </div>
                              {((step.output.ranked_documents as Array<Record<string, unknown>>) || []).map((doc, j) => (
                                <div key={j} style={{
                                  padding: '6px 10px', marginBottom: '4px', borderRadius: '4px',
                                  background: j === 0 ? 'var(--rh-color--success-bg)' : 'var(--rh-color--surface-secondary)',
                                  border: `1px solid ${j === 0 ? 'var(--rh-color--success)' : 'var(--rh-color--border)'}`,
                                  display: 'flex', alignItems: 'center', gap: '8px',
                                }}>
                                  <span style={{ fontWeight: 700, fontSize: '1rem', minWidth: '24px' }}>#{doc.rank as number}</span>
                                  <div style={{ flex: 1 }}>
                                    <span style={{ fontWeight: 600 }}>{doc.title as string}</span>
                                  </div>
                                  <Label isCompact color={j === 0 ? 'green' : 'grey'}>
                                    {(doc.relevance as number)?.toFixed(3)}
                                  </Label>
                                </div>
                              ))}
                            </>
                          )}

                          {step.name === 'synthesize' && (
                            <>
                              <div style={{ fontWeight: 600, marginBottom: '6px' }}>Generated Answer:</div>
                              <div style={{
                                padding: '12px', borderRadius: '6px',
                                background: 'var(--rh-color--gaudi-bg)', border: '1px solid var(--rh-color--gaudi)',
                                whiteSpace: 'pre-wrap', lineHeight: '1.6',
                              }}>
                                {step.output.answer as string}
                              </div>
                              {(step.output.citations as Array<Record<string, unknown>>)?.length > 0 && (
                                <div style={{ marginTop: '8px' }}>
                                  <div style={{ fontWeight: 600, marginBottom: '4px', fontSize: '0.78rem' }}>Citations:</div>
                                  <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                                    {((step.output.citations as Array<Record<string, unknown>>) || []).map((c, j) => (
                                      <Label key={j} isCompact color="blue">{c.title as string}</Label>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </>
                          )}

                          {step.name === 'governance' && (
                            <div style={{
                              padding: '12px', borderRadius: '6px',
                              background: (step.output.decision as string) === 'pass' ? 'var(--rh-color--success-bg)' : 'var(--rh-color--gaudi-bg)',
                              border: `1px solid ${(step.output.decision as string) === 'pass' ? 'var(--rh-color--success)' : 'var(--rh-color--gaudi)'}`,
                            }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                <Label color={(step.output.decision as string) === 'pass' ? 'green' : 'orange'} style={{ fontSize: '0.88rem', padding: '4px 12px' }}>
                                  {(step.output.decision as string)?.toUpperCase()}
                                </Label>
                              </div>
                              <div style={{ fontSize: '0.82rem' }}>{step.output.reason as string}</div>
                            </div>
                          )}
                        </CardBody>
                      </Card>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </PageSection>
      )}

      {/* Final answer */}
      {finalAnswer && (
        <PageSection variant="secondary">
          <Card>
            <CardBody>
              <Content component="h2" style={{ marginBottom: '0.75rem' }}>Research Answer</Content>
              <div style={{
                padding: '16px', borderRadius: '8px', background: 'var(--rh-color--surface)',
                border: '1px solid var(--rh-color--border)', whiteSpace: 'pre-wrap', lineHeight: '1.7',
                fontSize: '0.92rem',
              }}>
                {finalAnswer}
              </div>
              {citations.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <Content component="h4" style={{ marginBottom: '6px' }}>Sources</Content>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {citations.map((c, i) => (
                      <Label key={i} color="blue" isCompact>{c.title} ({(c.relevance * 100).toFixed(0)}%)</Label>
                    ))}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        </PageSection>
      )}
    </>
  );
}
