import { useState, useEffect, useRef } from 'react';
import {
  Card, CardBody, CardTitle, Content, Button, Label, TextArea,
  Split, SplitItem, Divider, CodeBlock, CodeBlockCode,
  ExpandableSection, Spinner, Alert, MenuToggle, Select, SelectOption,
} from '@patternfly/react-core';
import { ArrowRightIcon } from '@patternfly/react-icons';
import HardwareBadge from './HardwareBadge';
import { api } from '../api/client';
import type { RouteResponse } from '../api/types';

const TASKS = [
  { value: 'completion', label: 'Completion (LLM)', description: 'Text generation — routes by model size' },
  { value: 'embeddings', label: 'Embeddings', description: 'Vector encoding — routes to Xeon 6' },
  { value: 'classification', label: 'Classification', description: 'Categorization — routes to Xeon 6' },
  { value: 'reranking', label: 'Reranking', description: 'Cross-encoder scoring — routes to Xeon 6' },
];

const SIZE_MARKS = [
  { value: 1, label: 'Tiny', model: 'granite-4-0-h-tiny' },
  { value: 7, label: '7B', model: 'codellama-7b-instruct' },
  { value: 8, label: '8B', model: 'granite-3-2-8b-instruct' },
  { value: 14, label: '14B', model: 'deepseek-r1-distill-qwen-14b' },
  { value: 17, label: '17B', model: 'llama-scout-17b' },
];

const MODEL_FOR_TASK: Record<string, string> = {
  embeddings: 'nomic-embed-text-v1-5',
  classification: 'granite-4-0-h-tiny',
  reranking: 'codellama-7b-instruct',
};

const MAX_PROMPT_LENGTH = 500;
const COOLDOWN_MS = 3000;

function predictRoute(task: string, modelSize: number): { backend: string; hw: string; reason: string } {
  if (task === 'embeddings') return { backend: 'litellm-cpu', hw: 'xeon6', reason: 'nomic-embed-text-v1-5 on Xeon 6 — 768-dim embeddings' };
  if (task === 'classification') return { backend: 'litellm-cpu', hw: 'xeon6', reason: 'granite-4-0-h-tiny on Xeon 6 — fast classification' };
  if (task === 'reranking') return { backend: 'litellm-cpu', hw: 'xeon6', reason: 'codellama-7b on Xeon 6 — cross-encoder reranking' };
  if (task === 'completion' && modelSize <= 8) return { backend: 'litellm-cpu', hw: 'xeon6', reason: `${modelSize}B model on Xeon 6 — CPU-efficient with AMX` };
  return { backend: 'litellm-gpu', hw: 'gaudi', reason: `${modelSize}B model on Gaudi — needs HBM and tensor cores` };
}

export default function BuildYourOwn() {
  const [task, setTask] = useState('completion');
  const [taskOpen, setTaskOpen] = useState(false);
  const [modelSize, setModelSize] = useState(7);
  const [prompt, setPrompt] = useState('Explain the benefits of hardware-aware AI inference routing in one paragraph.');
  const [sending, setSending] = useState(false);
  const [response, setResponse] = useState<RouteResponse | null>(null);
  const [error, setError] = useState('');
  const [showRaw, setShowRaw] = useState(false);
  const [cooldown, setCooldown] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  const prediction = predictRoute(task, modelSize);
  const showSizeSlider = task === 'completion';
  const promptTooLong = prompt.length > MAX_PROMPT_LENGTH;
  const promptEmpty = prompt.trim().length < 3;

  useEffect(() => {
    setResponse(null);
    setError('');
  }, [task, modelSize]);

  const handleSend = async () => {
    if (promptEmpty || promptTooLong || cooldown) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setSending(true);
    setError('');
    setShowRaw(false);
    setCooldown(true);
    setTimeout(() => setCooldown(false), COOLDOWN_MS);

    const selectedModel = task === 'completion'
      ? SIZE_MARKS.find(m => m.value === modelSize)?.model || 'codellama-7b-instruct'
      : MODEL_FOR_TASK[task] || 'granite-4-0-h-tiny';

    const sanitized = prompt
      .slice(0, MAX_PROMPT_LENGTH)
      .replace(/(?:system\s*:|assistant\s*:|<<\s*SYS\s*>>|<\|im_start\|>|<\|im_end\|>|\[INST\]|\[\/INST\])/gi, '[filtered]')
      .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');

    try {
      const result = await api.routeRequest({
        task,
        prompt: sanitized,
        text: sanitized,
        model: selectedModel,
        model_size_b: modelSize,
        max_tokens: task === 'completion' ? 60 : 16,
        temperature: 0.3,
      }, abortRef.current.signal);
      setResponse(result);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Request failed');
    }
    setSending(false);
  };

  const matched = response && response.routing.selected_backend === prediction.backend;

  return (
    <div style={{ maxWidth: '700px' }}>
      <Card>
        <CardTitle>Build Your Own Request</CardTitle>
        <CardBody>
          <Content component="p" style={{ marginBottom: '1rem', color: 'var(--pf-t--global--text--color--subtle)' }}>
            Pick a task and a model size. Watch how the routing decision changes — lightweight
            tasks stay on Xeon 6, heavy models route to Gaudi. This is intelligent routing in action.
          </Content>

          {/* Task selector */}
          <div style={{ marginBottom: '1rem' }}>
            <Content component="small" style={{ display: 'block', marginBottom: '4px', fontWeight: 600 }}>Task Type</Content>
            <Select
              toggle={(ref) => (
                <MenuToggle ref={ref} onClick={() => setTaskOpen(!taskOpen)} isExpanded={taskOpen} style={{ width: '300px' }}>
                  {TASKS.find(t => t.value === task)?.label || task}
                </MenuToggle>
              )}
              isOpen={taskOpen}
              onSelect={(_e, value) => { setTask(value as string); setTaskOpen(false); }}
              onOpenChange={setTaskOpen}
              selected={task}
            >
              {TASKS.map(t => (
                <SelectOption key={t.value} value={t.value} description={t.description}>
                  {t.label}
                </SelectOption>
              ))}
            </Select>
          </div>

          {/* Model size selector */}
          {showSizeSlider && (
            <div style={{ marginBottom: '1.5rem' }}>
              <Content component="small" style={{ display: 'block', marginBottom: '8px', fontWeight: 600 }}>
                Model Size
              </Content>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {SIZE_MARKS.map(m => {
                  const isSelected = modelSize === m.value;
                  const isGaudi = m.value > 8;
                  return (
                    <button
                      key={m.value}
                      aria-pressed={modelSize === m.value}
                      onClick={() => setModelSize(m.value)}
                      style={{
                        padding: '8px 20px',
                        borderRadius: '6px',
                        border: `2px solid ${isSelected ? (isGaudi ? 'var(--rh-color--gaudi)' : 'var(--rh-color--xeon6)') : 'var(--rh-color--border)'}`,
                        background: isSelected ? (isGaudi ? 'var(--rh-color--gaudi-bg)' : 'var(--rh-color--xeon6-bg)') : 'var(--rh-color--surface)',
                        cursor: 'pointer',
                        fontWeight: isSelected ? 700 : 400,
                        fontSize: '0.9rem',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      {m.label}
                    </button>
                  );
                })}
              </div>
              <Content component="small" style={{ display: 'block', marginTop: '8px', color: 'var(--pf-t--global--text--color--subtle)' }}>
                {SIZE_MARKS.find(m => m.value === modelSize)?.model || ''} — {modelSize <= 8
                  ? `routes to Xeon 6 (≤ 8B threshold)`
                  : `routes to Gaudi (> 8B threshold)`}
              </Content>
            </div>
          )}

          {/* Prompt input */}
          <div style={{ marginBottom: '1rem' }}>
            <Content component="small" style={{ display: 'block', marginBottom: '4px', fontWeight: 600 }}>Prompt</Content>
            <TextArea
              value={prompt}
              onChange={(_e, val) => setPrompt(val)}
              aria-label="Request prompt"
              rows={2}
              validated={promptTooLong ? 'error' : promptEmpty ? 'warning' : 'default'}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', fontSize: '0.75rem' }}>
              <span style={{ color: promptEmpty ? 'var(--rh-color--gaudi)' : 'var(--pf-t--global--text--color--subtle)' }}>
                {promptEmpty ? 'Minimum 3 characters required' : ''}
              </span>
              <span style={{ color: promptTooLong ? 'var(--rh-color--brand)' : 'var(--pf-t--global--text--color--subtle)' }}>
                {prompt.length}/{MAX_PROMPT_LENGTH}
              </span>
            </div>
          </div>

          <Divider style={{ margin: '1rem 0' }} />

          {/* Prediction */}
          <div style={{
            padding: '12px 16px', borderRadius: '8px', marginBottom: '1rem',
            background: prediction.hw === 'gaudi' ? 'var(--rh-color--gaudi-bg)' : 'var(--rh-color--xeon6-bg)',
            border: `1px solid ${prediction.hw === 'gaudi' ? 'var(--rh-color--gaudi)' : 'var(--rh-color--xeon6)'}`,
          }}>
            <Split hasGutter>
              <SplitItem>
                <Content component="small" style={{ fontWeight: 600 }}>Predicted route:</Content>
              </SplitItem>
              <SplitItem>
                <HardwareBadge accelerator={prediction.hw} />
              </SplitItem>
              <SplitItem>
                <strong>{prediction.backend}</strong>
              </SplitItem>
            </Split>
            <Content component="small" style={{ display: 'block', marginTop: '4px', color: 'var(--pf-t--global--text--color--subtle)' }}>
              {prediction.reason}
            </Content>
          </div>

          <Button
            variant="primary"
            onClick={handleSend}
            isLoading={sending}
            isDisabled={promptEmpty || promptTooLong || sending || cooldown}
          >
            {cooldown ? 'Please wait...' : 'Send to Gateway'} <ArrowRightIcon style={{ marginLeft: '0.5rem' }} />
          </Button>
        </CardBody>
      </Card>

      {/* Result */}
      {sending && <div style={{ marginTop: '1rem' }}><Spinner aria-label="Routing request" /> Routing...</div>}

      {error && <Alert variant="danger" title="Request failed" style={{ marginTop: '1rem' }}>{error}</Alert>}

      {response && (
        <Card style={{ marginTop: '1rem' }}>
          <CardTitle>
            <Split hasGutter>
              <SplitItem>Routing Result</SplitItem>
              <SplitItem>
                <Label color={matched ? 'green' : 'orange'} isCompact>
                  {matched ? 'Prediction matched' : 'Different route!'}
                </Label>
              </SplitItem>
            </Split>
          </CardTitle>
          <CardBody>
            <Split hasGutter style={{ fontSize: '1rem' }}>
              <SplitItem>
                <strong>Backend:</strong> {response.routing.selected_backend}
              </SplitItem>
              <SplitItem>
                <HardwareBadge accelerator={response.routing.accelerator} />
              </SplitItem>
              <SplitItem>
                <strong>Latency:</strong> {response.routing.latency_ms?.toFixed(0)}ms
              </SplitItem>
              <SplitItem>
                <strong>Cost:</strong> ${response.routing.cost_estimate_per_1k_tokens}/1K
              </SplitItem>
            </Split>
            <Content component="p" style={{ marginTop: '0.5rem' }}>
              <strong>Why:</strong> <em>{response.routing.reason}</em>
            </Content>

            {response.result != null && (
              <>
                <Divider style={{ margin: '1rem 0' }} />
                <Content component="h4">Inference Result</Content>
                <div style={{
                  background: 'var(--pf-t--global--background--color--secondary--default)',
                  borderRadius: '6px', padding: '1rem', marginTop: '0.5rem',
                  fontFamily: 'var(--pf-t--global--font--family--mono)', fontSize: '0.88rem',
                  whiteSpace: 'pre-wrap',
                }}>
                  {(() => {
                    const r = response.result as Record<string, unknown> | null;
                    if (!r) return 'No result';
                    const choices = r.choices as Array<Record<string, unknown>> | undefined;
                    if (choices?.[0]) {
                      const c = choices[0];
                      const text = (c.text as string) || ((c.message as Record<string, unknown>)?.content as string);
                      if (text) return text;
                    }
                    const data = r.data as Array<Record<string, unknown>> | undefined;
                    if (data?.[0]?.embedding) return `Embedding vector (${(data[0].embedding as number[]).length} dimensions)\n\n[${(data[0].embedding as number[]).slice(0, 8).map(v => v.toFixed(4)).join(', ')}...]`;
                    if (r.predictions) return (r.predictions as Array<Record<string, unknown>>).map(p => `${p.label}: ${p.score}`).join('\n');
                    return JSON.stringify(r, null, 2).slice(0, 500);
                  })()}
                </div>
              </>
            )}

            <ExpandableSection
              toggleText={showRaw ? 'Hide raw response' : 'Show raw response'}
              onToggle={(_e, expanded) => setShowRaw(expanded)}
              isExpanded={showRaw}
              style={{ marginTop: '0.75rem' }}
            >
              <CodeBlock>
                <CodeBlockCode>{JSON.stringify(response, null, 2)}</CodeBlockCode>
              </CodeBlock>
            </ExpandableSection>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
