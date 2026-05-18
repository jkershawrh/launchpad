import { useState, useCallback, useEffect, useRef } from 'react';
import { Label, Spinner, Button, CodeBlock, CodeBlockCode, ExpandableSection } from '@patternfly/react-core';
import { CheckCircleIcon, ExclamationCircleIcon, AngleRightIcon, AngleDownIcon } from '@patternfly/react-icons';
import type { Accelerator } from '../api/types';
import { api } from '../api/client';
import { hwColors } from '../constants/hwColors';

export interface WorkflowStep {
  label: string;
  hw: Accelerator;
  task: string;
  model_size_b?: number;
  local?: boolean;
}

interface StepResult {
  status: 'pending' | 'running' | 'done' | 'error';
  latency_ms?: number;
  backend?: string;
  accelerator?: string;
  reason?: string;
  error?: string;
  result?: unknown;
  requestPayload?: Record<string, unknown>;
}

interface Props {
  title: string;
  subtitle: string;
  steps: WorkflowStep[];
  prompt: string;
  runTrigger?: number;
}

/* hwColors imported from ../constants/hwColors */

const taskEmoji: Record<string, string> = {
  embeddings: 'E',
  search: 'S',
  reranking: 'R',
  classification: 'C',
  completion: 'G',
  batch_generation: 'G',
  governance: 'V',
  policy: 'P',
};

const taskDescriptions: Record<string, string> = {
  embeddings: 'Convert text into dense vector representations for semantic search',
  search: 'Find the most relevant documents using cosine similarity against the knowledge base',
  reranking: 'Re-score candidate documents by relevance to the query',
  classification: 'Categorize input text into predefined labels',
  completion: 'Generate natural language continuation from the prompt',
  batch_generation: 'Generate completions for multiple prompts in batch',
  governance: 'Evaluate action risk level and determine approval, escalation, or denial',
  policy: 'Check action compliance against security policies and flag violations',
};

function formatResponsePreview(task: string, result: unknown): string {
  const r = result as Record<string, unknown>;
  if (task === 'completion' || task === 'batch_generation') {
    const choices = r?.choices as Array<Record<string, unknown>> | undefined;
    const choice = choices?.[0];
    const text = (choice?.text as string) || (choice?.message as Record<string, unknown>)?.content as string;
    return text?.trim() || '(empty response)';
  }
  if (task === 'embeddings') {
    const data = r?.data as Array<unknown> | undefined;
    const emb = (data?.[0] as Record<string, unknown>)?.embedding as number[] | undefined;
    return `${data?.length || 0} embedding(s), ${emb?.length || '?'} dimensions`;
  }
  if (task === 'search') {
    const results = r?.results as Array<Record<string, unknown>> | undefined;
    const total = r?.total_documents as number | undefined;
    return `${results?.length || 0} results from ${total || '?'} documents`;
  }
  if (task === 'reranking') {
    const results = r?.results as Array<Record<string, unknown>> | undefined;
    return `${results?.length || 0} documents re-ranked by relevance`;
  }
  if (task === 'classification') {
    const preds = r?.predictions as Array<Record<string, unknown>> | undefined;
    return preds?.map(p => `${p.label}: ${(p.score as number)?.toFixed(2)}`).join(', ') || 'No predictions';
  }
  if (task === 'governance') {
    return `${(r?.decision as string || 'unknown').toUpperCase()} — Risk: ${r?.risk_level || '?'} — ${(r?.justification as string)?.slice(0, 100) || ''}`;
  }
  if (task === 'policy') {
    const verdict = r?.verdict as string || 'unknown';
    const violations = r?.violations as string[] || [];
    return `${verdict.toUpperCase()}${violations.length ? ` — ${violations.join('; ')}` : ' — No violations'}`;
  }
  return JSON.stringify(r).slice(0, 200);
}

function InfoCard({ title, children }: { icon?: string; title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--rh-color--surface)', borderRadius: '8px', border: '1px solid var(--rh-color--border)',
      overflow: 'hidden', marginBottom: '8px',
    }}>
      <div style={{
        padding: '8px 12px', background: 'var(--rh-color--surface-secondary)', borderBottom: '1px solid var(--rh-color--border)',
        fontWeight: 700, fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)',
      }}>
        {title}
      </div>
      <div style={{ padding: '10px 12px' }}>{children}</div>
    </div>
  );
}

function TimingBar({ label, ms, maxMs }: { label: string; ms: number; maxMs: number }) {
  const pct = Math.min((ms / maxMs) * 100, 100);
  return (
    <div style={{ marginBottom: '6px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '3px' }}>
        <span style={{ color: 'var(--rh-color--text-secondary)' }}>{label}</span>
        <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{ms < 1 ? '<1' : Math.round(ms).toLocaleString()}ms</span>
      </div>
      <div style={{ height: '6px', background: 'var(--rh-color--border)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: '3px',
          background: ms > 5000 ? 'var(--rh-color--gaudi)' : 'var(--rh-color--xeon6)',
          width: `${pct}%`, transition: 'width 0.5s ease',
        }} />
      </div>
    </div>
  );
}

function renderDetailPanel(step: WorkflowStep, r: StepResult, totalWorkflowMs: number) {
  const res = r.result as Record<string, unknown> | undefined;
  const usage = res?.usage as Record<string, number> | undefined;
  const model = res?.model as string | undefined;
  const localMs = res?._local_inference_ms as number | undefined;

  return (
    <div style={{
      margin: '8px 0 6px 0', padding: '12px',
      background: 'var(--rh-color--surface-tertiary)', borderRadius: '10px',
      border: '1px solid var(--rh-color--border)',
    }}>
      {/* Routing */}
      <InfoCard icon="ROUTE" title="Routing Decision">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.8rem' }}>
          <div>
            <div style={{ color: 'var(--rh-color--text-secondary)', fontSize: '0.7rem' }}>Task</div>
            <div style={{ fontWeight: 600 }}>{taskEmoji[step.task] || ''} {step.task}</div>
          </div>
          <div>
            <div style={{ color: 'var(--rh-color--text-secondary)', fontSize: '0.7rem' }}>Backend</div>
            <div style={{ fontWeight: 600 }}>{r.backend || 'unknown'}</div>
          </div>
          <div>
            <div style={{ color: 'var(--rh-color--text-secondary)', fontSize: '0.7rem' }}>Hardware</div>
            <Label color={hwColors[r.accelerator || '']?.labelColor || 'grey'} isCompact>{r.accelerator || step.hw}</Label>
          </div>
          {model && (
            <div>
              <div style={{ color: 'var(--rh-color--text-secondary)', fontSize: '0.7rem' }}>Model</div>
              <div style={{ fontWeight: 600, fontSize: '0.78rem' }}>{model.split('/').pop()}</div>
            </div>
          )}
        </div>
        <div style={{ marginTop: '8px', fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', fontStyle: 'italic' }}>
          {taskDescriptions[step.task]}
        </div>
        {r.reason && (
          <div style={{
            marginTop: '6px', padding: '6px 10px', background: 'var(--rh-color--xeon6-bg)',
            borderRadius: '4px', fontSize: '0.78rem', borderLeft: '3px solid var(--rh-color--xeon6)',
          }}>
            {r.reason}
          </div>
        )}
      </InfoCard>

      {/* Timing */}
      <InfoCard icon="PERF" title="Performance">
        {r.latency_ms != null && (
          <TimingBar label="Total latency" ms={r.latency_ms} maxMs={Math.max(totalWorkflowMs, r.latency_ms)} />
        )}
        {localMs != null && (
          <TimingBar label="Model inference" ms={localMs} maxMs={Math.max(totalWorkflowMs, localMs)} />
        )}
        {usage && (
          <div style={{
            display: 'flex', gap: '16px', marginTop: '8px', fontSize: '0.78rem',
            padding: '8px 10px', background: 'var(--rh-color--surface-secondary)', borderRadius: '6px',
          }}>
            <div><span style={{ color: 'var(--rh-color--text-secondary)' }}>Input:</span> <strong>{usage.prompt_tokens || 0}</strong> tokens</div>
            <div><span style={{ color: 'var(--rh-color--text-secondary)' }}>Output:</span> <strong>{usage.completion_tokens || 0}</strong> tokens</div>
            <div><span style={{ color: 'var(--rh-color--text-secondary)' }}>Total:</span> <strong>{usage.total_tokens || 0}</strong> tokens</div>
          </div>
        )}
      </InfoCard>

      {/* Response */}
      {res && (
        <InfoCard icon={taskEmoji[step.task] || 'R'} title="Response">
          {(step.task === 'completion' || step.task === 'batch_generation') ? (
            <div style={{
              padding: '12px 14px', background: 'var(--rh-color--surface-tertiary)', borderRadius: '6px',
              fontSize: '0.85rem', lineHeight: '1.6', whiteSpace: 'pre-wrap',
              borderLeft: '3px solid var(--rh-color--success)',
            }}>
              {formatResponsePreview(step.task, res)}
            </div>
          ) : (step.task === 'embeddings') ? (
            <div>
              <div style={{
                padding: '8px 12px', background: 'var(--rh-color--xeon6-bg)', borderRadius: '6px',
                fontSize: '0.82rem', marginBottom: '8px', fontWeight: 600,
              }}>
                {formatResponsePreview(step.task, res)}
              </div>
              <div style={{
                padding: '8px 10px', background: 'var(--rh-color--surface-secondary)', borderRadius: '4px',
                fontFamily: 'monospace', fontSize: '0.7rem', overflow: 'auto',
                color: 'var(--rh-color--text-secondary)',
              }}>
                [{((res.data as Array<Record<string, unknown>>)?.[0]?.embedding as number[])
                  ?.slice(0, 12).map(v => v.toFixed(4)).join(', ')}...]
              </div>
            </div>
          ) : (step.task === 'search' || step.task === 'reranking') ? (
            <div>
              {((res.results as Array<Record<string, unknown>>) || []).map((doc, idx) => (
                <div key={idx} style={{
                  display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px',
                  background: idx % 2 === 0 ? 'var(--rh-color--surface-tertiary)' : 'var(--rh-color--surface)', borderRadius: '4px',
                  marginBottom: '2px',
                }}>
                  <div style={{
                    width: '24px', height: '24px', borderRadius: '50%',
                    background: idx === 0 ? 'var(--rh-color--success)' : 'var(--rh-color--text-secondary)',
                    color: 'var(--rh-color--text-on-dark)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '0.7rem', fontWeight: 700, flexShrink: 0,
                  }}>
                    {idx + 1}
                  </div>
                  <div style={{ flex: 1, fontSize: '0.78rem', lineHeight: '1.4' }}>
                    {(doc.text as string) || '—'}
                  </div>
                  <div style={{
                    padding: '2px 8px', borderRadius: '10px', fontSize: '0.72rem', fontWeight: 700,
                    background: ((doc.relevance_score ?? doc.score) as number) > 0.7 ? 'var(--rh-color--success-bg)' : 'var(--rh-color--surface-secondary)',
                    fontFamily: 'monospace', flexShrink: 0,
                  }}>
                    {((doc.relevance_score ?? doc.score) as number)?.toFixed(3)}
                  </div>
                </div>
              ))}
            </div>
          ) : (step.task === 'classification') ? (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {((res.predictions as Array<Record<string, unknown>>) || []).map((p, idx) => (
                <div key={idx} style={{
                  padding: '6px 14px', borderRadius: '20px',
                  background: idx === 0 ? 'var(--rh-color--success-bg)' : 'var(--rh-color--surface-secondary)',
                  fontSize: '0.8rem', fontWeight: idx === 0 ? 700 : 400,
                  border: idx === 0 ? '1px solid var(--rh-color--success)' : '1px solid var(--rh-color--border)',
                }}>
                  {p.label as string} <span style={{ fontFamily: 'monospace', opacity: 0.7 }}>{(p.score as number)?.toFixed(2)}</span>
                </div>
              ))}
            </div>
          ) : (step.task === 'governance') ? (
            <div>
              <div style={{
                display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '10px',
              }}>
                <div style={{
                  padding: '6px 16px', borderRadius: '20px', fontWeight: 700, fontSize: '0.85rem',
                  background: (res.decision as string) === 'approve' ? 'var(--rh-color--success-bg)' :
                    (res.decision as string) === 'deny' ? 'var(--rh-color--brand-light)' : 'var(--rh-color--gaudi-bg)',
                  border: `1px solid ${(res.decision as string) === 'approve' ? 'var(--rh-color--success)' :
                    (res.decision as string) === 'deny' ? 'var(--rh-color--brand)' : 'var(--rh-color--gaudi)'}`,
                  color: (res.decision as string) === 'deny' ? 'var(--rh-color--brand-dark)' : 'inherit',
                }}>
                  {(res.decision as string || 'unknown').toUpperCase()}
                </div>
                <Label color={(res.risk_level as string) === 'low' ? 'green' :
                  (res.risk_level as string) === 'critical' ? 'red' :
                  (res.risk_level as string) === 'high' ? 'red' : 'orange'} isCompact>
                  Risk: {res.risk_level as string}
                </Label>
              </div>
              <div style={{
                padding: '10px 12px', background: 'var(--rh-color--surface-tertiary)', borderRadius: '6px',
                fontSize: '0.82rem', lineHeight: '1.5',
              }}>
                {res.justification as string}
              </div>
            </div>
          ) : (step.task === 'policy') ? (
            <div>
              <div style={{
                display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '10px',
              }}>
                <div style={{
                  padding: '6px 16px', borderRadius: '20px', fontWeight: 700, fontSize: '0.85rem',
                  background: (res.verdict as string) === 'pass' ? 'var(--rh-color--success-bg)' : 'var(--rh-color--brand-light)',
                  border: `1px solid ${(res.verdict as string) === 'pass' ? 'var(--rh-color--success)' : 'var(--rh-color--brand)'}`,
                  color: (res.verdict as string) === 'pass' ? 'var(--rh-color--success)' : 'var(--rh-color--brand-dark)',
                }}>
                  {(res.verdict as string || 'unknown').toUpperCase()}
                </div>
              </div>
              {((res.violations as string[]) || []).length > 0 && (
                <div style={{ marginBottom: '10px' }}>
                  {(res.violations as string[]).map((v, idx) => (
                    <div key={idx} style={{
                      padding: '6px 10px', marginBottom: '4px',
                      background: 'var(--rh-color--brand-light)', borderRadius: '4px',
                      borderLeft: '3px solid var(--rh-color--brand)',
                      fontSize: '0.8rem',
                    }}>
                      {v}
                    </div>
                  ))}
                </div>
              )}
              <div style={{
                padding: '10px 12px', background: 'var(--rh-color--surface-tertiary)', borderRadius: '6px',
                fontSize: '0.82rem', lineHeight: '1.5',
              }}>
                {res.analysis as string}
              </div>
            </div>
          ) : (
            <pre style={{
              background: 'var(--rh-color--surface-secondary)', padding: '10px', borderRadius: '4px',
              fontSize: '0.73rem', overflow: 'auto', margin: 0,
            }}>{JSON.stringify(res, null, 2)}</pre>
          )}
        </InfoCard>
      )}

      {/* Request payload (collapsed by default) */}
      {r.requestPayload && (
        <details style={{ fontSize: '0.75rem', color: 'var(--rh-color--text-secondary)', marginTop: '4px' }}>
          <summary style={{ cursor: 'pointer', userSelect: 'none' }}>View request payload</summary>
          <pre style={{
            marginTop: '6px', padding: '8px 10px', background: 'var(--rh-color--surface-secondary)',
            borderRadius: '4px', fontSize: '0.7rem', overflow: 'auto',
          }}>{JSON.stringify(r.requestPayload, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

export default function LiveWorkflow({ title, subtitle, steps, prompt, runTrigger }: Props) {
  const [results, setResults] = useState<StepResult[]>(steps.map(() => ({ status: 'pending' })));
  const [running, setRunning] = useState(false);
  const [totalMs, setTotalMs] = useState(0);
  const [showRaw, setShowRaw] = useState(false);
  const [expandedStep, setExpandedStep] = useState<number | null>(null);
  const lastTrigger = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  const updateStep = (index: number, update: Partial<StepResult>) => {
    setResults(prev => prev.map((r, i) => i === index ? { ...r, ...update } : r));
  };

  const executeWorkflow = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setRunning(true);
    setTotalMs(0);
    setShowRaw(false);
    setExpandedStep(null);
    setResults(steps.map(() => ({ status: 'pending' })));

    const start = performance.now();
    let searchContext = '';
    let searchDocTexts: string[] = [];

    for (let i = 0; i < steps.length; i++) {
      if (abortRef.current?.signal.aborted) break;
      const step = steps[i];
      updateStep(i, { status: 'running' });

      if (step.local) {
        await new Promise(r => setTimeout(r, 50));
        updateStep(i, {
          status: 'done', latency_ms: 0.5,
          backend: 'local', accelerator: 'local',
          reason: 'Local operation — no gateway call needed',
        });
        continue;
      }

      let stepPrompt = prompt;
      if (step.task === 'completion' && searchContext) {
        stepPrompt = `Based on the following context, answer the question.\n\nContext:\n${searchContext}\n\nQuestion: ${prompt}`;
      }

      const modelForTask: Record<string, string> = {
        completion: step.model_size_b && step.model_size_b > 8 ? 'llama-scout-17b' : 'codellama-7b-instruct',
        embeddings: 'nomic-embed-text-v1-5',
        search: 'nomic-embed-text-v1-5',
        reranking: 'codellama-7b-instruct',
        classification: 'granite-4-0-h-tiny',
        governance: 'granite-4-0-h-tiny',
        policy: 'granite-4-0-h-tiny',
        batch_generation: 'deepseek-r1-distill-qwen-14b',
      };

      const payload: Record<string, unknown> = {
        task: step.task,
        prompt: stepPrompt,
        text: stepPrompt,
        model: modelForTask[step.task] || 'granite-3-2-8b-instruct',
        model_size_b: step.model_size_b || 0,
        max_tokens: step.task === 'completion' ? 60 : step.task === 'governance' || step.task === 'policy' ? 40 : 16,
        temperature: 0.3,
      };

      if (step.task === 'reranking' && searchDocTexts.length > 0) {
        payload.texts = searchDocTexts;
      }

      try {
        const response = await api.routeRequest(payload);

        if (step.task === 'search' && response.result) {
          const searchResults = (response.result as Record<string, unknown>)?.results as Array<Record<string, unknown>> | undefined;
          if (searchResults?.length) {
            searchDocTexts = searchResults.map(r => r.text as string);
            searchContext = searchResults.map((r, idx) => `[${idx + 1}] ${r.text as string}`).join('\n');
          }
        }
        if (step.task === 'reranking' && response.result) {
          const reranked = (response.result as Record<string, unknown>)?.results as Array<Record<string, unknown>> | undefined;
          if (reranked?.length) {
            searchContext = reranked.slice(0, 3).map((r, idx) => `[${idx + 1}] ${r.text as string}`).join('\n');
          }
        }

        updateStep(i, {
          status: 'done',
          latency_ms: response.routing?.latency_ms || 0,
          backend: response.routing?.selected_backend || 'unknown',
          accelerator: response.routing?.accelerator || step.hw,
          reason: response.routing?.reason || '',
          result: response.result,
          requestPayload: payload,
        });
      } catch (err) {
        updateStep(i, {
          status: 'error',
          error: err instanceof Error ? err.message : 'Request failed',
          requestPayload: payload,
        });
        break;
      }
    }

    setTotalMs(performance.now() - start);
    setRunning(false);
  }, [steps, prompt]);

  useEffect(() => {
    if (runTrigger && runTrigger !== lastTrigger.current && !running) {
      lastTrigger.current = runTrigger;
      executeWorkflow();
    }
  }, [runTrigger, running, executeWorkflow]);

  const xeonCount = steps.filter(s => s.hw === 'xeon6').length;
  const gaudiCount = steps.filter(s => s.hw === 'gaudi').length;
  const localCount = steps.filter(s => s.hw === 'local').length;
  const allDone = results.every(r => r.status === 'done');

  return (
    <div style={{ maxWidth: '600px' }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px',
        background: 'var(--pf-t--global--background--color--primary--default)',
        borderRadius: '12px 12px 0 0',
        border: '1px solid var(--pf-t--global--border--color--default)',
        borderBottom: 'none',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: '1rem' }}>{title}</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--pf-t--global--text--color--subtle)' }}>{subtitle}</div>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={executeWorkflow}
          isLoading={running}
          isDisabled={running}
        >
          {running ? 'Running...' : allDone ? 'Run Again' : 'Run Workflow'}
        </Button>
      </div>

      {/* Steps */}
      <div style={{
        padding: '16px 20px',
        border: '1px solid var(--pf-t--global--border--color--default)',
        borderTop: 'none',
        background: 'var(--rh-color--surface)',
      }}>
        {steps.map((step, i) => {
          const r = results[i];
          const hw = hwColors[step.hw] || hwColors.local;
          const isRunning = r.status === 'running';
          const isDone = r.status === 'done';
          const isError = r.status === 'error';
          const isPending = r.status === 'pending';
          const isExpanded = expandedStep === i;
          const isClickable = isDone || isError;

          return (
            <div key={i}>
              <div
                role={isClickable ? 'button' : undefined}
                tabIndex={isClickable ? 0 : undefined}
                aria-expanded={isClickable ? isExpanded : undefined}
                onClick={isClickable ? () => setExpandedStep(isExpanded ? null : i) : undefined}
                onKeyDown={isClickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpandedStep(isExpanded ? null : i); } } : undefined}
                style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  padding: '12px 14px', borderRadius: '8px',
                  background: isDone ? hw.done : isRunning ? hw.bg : isError ? 'var(--rh-color--brand-light)' : 'var(--rh-color--surface-tertiary)',
                  border: `2px solid ${isRunning ? hw.color : isDone ? hw.color : isError ? 'var(--pf-t--global--danger--color--default, #c9190b)' : 'var(--rh-color--border)'}`,
                  opacity: isPending ? 0.5 : 1,
                  transition: 'all 0.3s ease',
                  animation: isRunning ? 'pulse 1.5s ease-in-out infinite' : 'none',
                  cursor: isClickable ? 'pointer' : 'default',
                }}>
                {/* Step number */}
                <div style={{
                  width: '28px', height: '28px', borderRadius: '50%',
                  background: isDone ? 'var(--rh-color--success)' : isRunning ? hw.color : isError ? 'var(--pf-t--global--danger--color--default, #c9190b)' : 'var(--rh-color--border)',
                  color: 'var(--rh-color--text-on-dark)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.8rem', fontWeight: 700, flexShrink: 0,
                  transition: 'all 0.3s ease',
                }}>
                  {isDone ? <CheckCircleIcon /> : isError ? <ExclamationCircleIcon /> : isRunning ? <Spinner size="sm" aria-label="Loading" /> : i + 1}
                </div>

                {/* Label + summary */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>{step.label}</div>
                  <div style={{
                    fontSize: '0.75rem', color: 'var(--pf-t--global--text--color--subtle)',
                  }}>
                    {isDone && r.result != null
                      ? formatResponsePreview(step.task, r.result)
                      : isDone && r.reason ? r.reason
                      : isError ? r.error
                      : isRunning ? 'Routing to backend...' : ''}
                  </div>
                </div>

                {/* Hardware badge */}
                <Label color={isDone ? hw.labelColor : 'grey'} isCompact style={{ flexShrink: 0 }}>
                  {isDone && r.backend ? r.backend : step.hw === 'xeon6' ? 'Xeon 6' : step.hw === 'gaudi' ? 'Gaudi' : 'Local'}
                </Label>

                {/* Latency */}
                <div style={{
                  fontFamily: 'var(--pf-t--global--font--family--mono)',
                  fontSize: '0.8rem', fontWeight: 600, width: '70px', textAlign: 'right',
                  color: isDone ? 'var(--rh-color--success)' : 'var(--pf-t--global--text--color--subtle)',
                }}>
                  {isDone ? `${r.latency_ms! < 1 ? '<1' : Math.round(r.latency_ms!)}ms` : isRunning ? '...' : ''}
                </div>

                {/* Expand chevron */}
                {isClickable && (
                  <div style={{ color: 'var(--rh-color--text-secondary)', flexShrink: 0, fontSize: '0.85rem' }}>
                    {isExpanded ? <AngleDownIcon /> : <AngleRightIcon />}
                  </div>
                )}
              </div>

              {/* Expanded detail panel */}
              {isExpanded && isDone && renderDetailPanel(step, r, totalMs)}
              {isExpanded && isError && (
                <div style={{
                  margin: '8px 0 6px 0', padding: '12px 16px',
                  background: 'var(--rh-color--brand-light)', borderRadius: '10px', border: '1px solid var(--pf-t--global--danger--color--default, #c9190b)',
                  fontSize: '0.8rem',
                }}>
                  <div style={{ fontWeight: 700, marginBottom: '4px' }}>Error Details</div>
                  <div style={{ marginBottom: '8px' }}>{r.error}</div>
                  {r.requestPayload && (
                    <details>
                      <summary style={{ cursor: 'pointer', fontSize: '0.75rem', color: 'var(--rh-color--text-secondary)' }}>View request payload</summary>
                      <pre style={{
                        marginTop: '6px', background: 'var(--rh-color--surface-secondary)', padding: '8px',
                        borderRadius: '4px', fontSize: '0.7rem', overflow: 'auto',
                      }}>{JSON.stringify(r.requestPayload, null, 2)}</pre>
                    </details>
                  )}
                </div>
              )}

              {/* Connector */}
              {i < steps.length - 1 && (
                <div style={{
                  width: '3px', height: '14px', margin: '0 auto',
                  background: isDone && results[i + 1]?.status !== 'pending'
                    ? `linear-gradient(${hwColors[step.hw]?.color || 'var(--rh-color--border)'}, ${hwColors[steps[i + 1].hw]?.color || 'var(--rh-color--border)'})`
                    : 'var(--rh-color--border)',
                  transition: 'all 0.3s ease',
                }} />
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{
        padding: '12px 20px',
        borderRadius: '0 0 12px 12px',
        border: '1px solid var(--pf-t--global--border--color--default)',
        borderTop: 'none',
        background: 'var(--pf-t--global--background--color--secondary--default)',
        fontSize: '0.82rem',
        display: 'flex', justifyContent: 'space-between',
      }}>
        <span>
          {xeonCount} on Xeon 6 &middot; {gaudiCount} on Gaudi{localCount > 0 ? ` · ${localCount} local` : ''}
        </span>
        <span style={{ fontWeight: 600 }}>
          {allDone ? `Total: ${Math.round(totalMs)}ms` : running ? 'Running...' : ''}
        </span>
      </div>

      {/* Raw JSON (expandable) */}
      {allDone && (
        <ExpandableSection
          toggleText={showRaw ? 'Hide raw JSON' : 'Show raw JSON'}
          onToggle={(_e, expanded) => setShowRaw(expanded)}
          isExpanded={showRaw}
          style={{ marginTop: '0.75rem' }}
        >
          <CodeBlock>
            <CodeBlockCode>{JSON.stringify(results.map((r, i) => ({
              step: steps[i].label,
              ...r,
            })), null, 2)}</CodeBlockCode>
          </CodeBlock>
        </ExpandableSection>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(0, 102, 204, 0.3); }
          50% { box-shadow: 0 0 0 6px rgba(0, 102, 204, 0); }
        }
      `}</style>
    </div>
  );
}
