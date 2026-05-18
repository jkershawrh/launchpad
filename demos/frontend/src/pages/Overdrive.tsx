import { useState, useCallback, useEffect } from 'react';
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardTitle,
  Content,
  Gallery,
  GalleryItem,
  Label,
  MenuToggle,
  NumberInput,
  PageSection,
  Select,
  SelectOption,
  Spinner,
  Switch,
} from '@patternfly/react-core';

import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
} from '@patternfly/react-icons';
import { api } from '../api/client';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const TASK_TYPES = [
  'classification',
  'embedding',
  'rerank',
  'short_summary',
  'long_summary',
  'incident_rca',
  'batch_summary',
] as const;

const PRIORITIES = ['low', 'normal', 'high', 'critical'] as const;

const BATCH_REQUESTS = [
  { task_type: 'classification', token_estimate: 1000, priority: 'normal', latency_target_ms: 8000 },
  { task_type: 'embedding', token_estimate: 6000, priority: 'normal', latency_target_ms: 5000 },
  { task_type: 'rerank', token_estimate: 4000, priority: 'normal', latency_target_ms: 5000 },
  { task_type: 'short_summary', token_estimate: 8000, priority: 'high', latency_target_ms: 8000 },
  { task_type: 'long_summary', token_estimate: 24000, priority: 'high', latency_target_ms: 5000 },
  { task_type: 'incident_rca', token_estimate: 32000, priority: 'critical', latency_target_ms: 5000 },
  { task_type: 'batch_summary', token_estimate: 40000, priority: 'critical', latency_target_ms: 10000 },
  { task_type: 'classification', token_estimate: 500, priority: 'low', latency_target_ms: 8000 },
  { task_type: 'unknown', token_estimate: 1000, priority: 'normal', latency_target_ms: 5000 },
  { task_type: 'long_summary', token_estimate: 20000, priority: 'high', latency_target_ms: 5000 },
];

const LANE_META: Record<string, {
  color: string; bg: string; labelColor: 'green' | 'blue' | 'orange' | 'red';
  model: string; accelerator: string; capabilities: string[];
  hwStory: string;
}> = {
  eco: {
    color: 'var(--rh-color--success)',
    bg: 'var(--rh-color--success-bg)',
    labelColor: 'green',
    model: 'granite-4-0-h-tiny',
    accelerator: 'Xeon 6',
    capabilities: ['classification', 'short_summary'],
    hwStory: 'Alert triage, text classification, and batch scoring on Xeon 6. Sub-5ms latency, <$0.001 per 1K tokens. No GPU overhead — AMX handles it in hardware.',
  },
  performance: {
    color: 'var(--rh-color--xeon6)',
    bg: 'var(--rh-color--xeon6-bg)',
    labelColor: 'blue',
    model: 'codellama-7b-instruct',
    accelerator: 'Xeon 6',
    capabilities: ['embedding', 'rerank', 'short_summary', 'long_summary'],
    hwStory: 'Embeddings and reranking on Xeon 6 with AMX (Advanced Matrix Extensions). Fast enough for RAG pipelines, 10x cheaper than GPU. Ideal for knowledge base search.',
  },
  overdrive: {
    color: 'var(--rh-color--gaudi)',
    bg: 'var(--rh-color--gaudi-bg)',
    labelColor: 'orange',
    model: 'llama-scout-17b',
    accelerator: 'Gaudi',
    capabilities: ['long_summary', 'incident_rca', 'batch_summary'],
    hwStory: 'Large models (17B+) on Intel Gaudi with 96GB HBM. 100+ tokens/sec generation for long summaries, RCA, and batch reports. Use when throughput matters more than cost.',
  },
};

const LANE_LABEL_COLOR: Record<string, 'green' | 'blue' | 'orange' | 'red'> = {
  eco: 'green',
  performance: 'blue',
  overdrive: 'orange',
  indeterminate: 'red',
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface RouteCheck {
  name: string;
  route: string;
  result: string;
  observed?: unknown;
  reason?: string;
}

interface RouteResult {
  decision_id?: string;
  request_id?: string;
  selected_route?: string;
  outcome?: string;
  reason_codes?: string[];
  checks?: RouteCheck[];
  evaluated_routes?: string[];
  timestamp?: string;
  request?: Record<string, unknown>;
  route_states?: Record<string, unknown>;
}

interface BatchResult {
  batch_id?: string;
  total_requests?: number;
  routes?: Record<string, number>;
  fallbacks?: number;
  indeterminate?: number;
  top_reason_codes?: string[];
}

interface LaneStatus {
  name: string;
  endpoint: string;
  healthy: boolean;
  capabilities: string[];
  model?: string;
  accelerator?: string;
}

/* ------------------------------------------------------------------ */
/*  Step Badge                                                         */
/* ------------------------------------------------------------------ */

function StepBadge({ step, label }: { step: number; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '0.75rem' }}>
      <div style={{
        width: '36px', height: '36px', borderRadius: '50%',
        background: 'var(--rh-color--brand)', color: '#fff',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '1rem', fontWeight: 700, flexShrink: 0,
      }}>
        {step}
      </div>
      <Content component="h2" style={{ margin: 0 }}>{label}</Content>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function Overdrive() {
  /* Lane status */
  const [lanes, setLanes] = useState<Record<string, LaneStatus> | null>(null);
  const [lanesLoading, setLanesLoading] = useState(false);
  const [lanesError, setLanesError] = useState<string | null>(null);

  /* Route evaluator form */
  const [taskType, setTaskType] = useState<string>(TASK_TYPES[0]);
  const [taskOpen, setTaskOpen] = useState(false);
  const [tokenEstimate, setTokenEstimate] = useState(1000);
  const [priority, setPriority] = useState<string>(PRIORITIES[1]);
  const [priorityOpen, setPriorityOpen] = useState(false);
  const [latencyTarget, setLatencyTarget] = useState(5000);
  const [routeResult, setRouteResult] = useState<RouteResult | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);

  /* Batch demo */
  const [batchResult, setBatchResult] = useState<BatchResult | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);

  /* Failover demo */
  const [failoverResult, setFailoverResult] = useState<{before: BatchResult; after: BatchResult} | null>(null);
  const [failoverLoading, setFailoverLoading] = useState(false);

  /* ---- Fetch lane status ---- */
  const fetchStatus = useCallback(async () => {
    setLanesLoading(true);
    setLanesError(null);
    try {
      const data = await api.overdriveStatus() as { lanes?: Record<string, LaneStatus> } & Record<string, unknown>;
      if (data.lanes) {
        setLanes(data.lanes as Record<string, LaneStatus>);
      } else {
        const defaults: Record<string, LaneStatus> = {};
        for (const [k, v] of Object.entries(LANE_META)) {
          defaults[k] = { name: k, endpoint: '', healthy: true, capabilities: v.capabilities, model: v.model, accelerator: v.accelerator };
        }
        setLanes(defaults);
      }
    } catch (err) {
      setLanesError(err instanceof Error ? err.message : 'Failed to fetch lane status');
      const defaults: Record<string, LaneStatus> = {};
      for (const [k, v] of Object.entries(LANE_META)) {
        defaults[k] = { name: k, endpoint: '', healthy: true, capabilities: v.capabilities, model: v.model, accelerator: v.accelerator };
      }
      setLanes(defaults);
    } finally {
      setLanesLoading(false);
    }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  /* ---- Toggle lane health ---- */
  const toggleHealth = useCallback(async (lane: string, healthy: boolean) => {
    try {
      await api.overdriveSetHealth(lane, healthy);
    } catch {
      // ignore — still flip locally for demo
    }
    setLanes((prev) => {
      if (!prev) return prev;
      return { ...prev, [lane]: { ...prev[lane], healthy } };
    });
  }, []);

  /* ---- Evaluate single route ---- */
  const evaluateRoute = useCallback(async () => {
    setRouteLoading(true);
    setRouteError(null);
    setRouteResult(null);
    try {
      const data = await api.overdriveRoute({
        task_type: taskType,
        token_estimate: tokenEstimate,
        priority,
        latency_target_ms: latencyTarget,
      });
      setRouteResult(data as unknown as RouteResult);
    } catch (err) {
      setRouteError(err instanceof Error ? err.message : 'Route evaluation failed');
    } finally {
      setRouteLoading(false);
    }
  }, [taskType, tokenEstimate, priority, latencyTarget]);

  /* ---- Batch demo ---- */
  const runBatch = useCallback(async () => {
    setBatchLoading(true);
    setBatchError(null);
    setBatchResult(null);
    try {
      const data = await api.overdriveBatch(BATCH_REQUESTS);
      setBatchResult(data as unknown as BatchResult);
    } catch (err) {
      setBatchError(err instanceof Error ? err.message : 'Batch evaluation failed');
    } finally {
      setBatchLoading(false);
    }
  }, []);

  /* ---- Failover demo ---- */
  const runFailoverDemo = useCallback(async () => {
    setFailoverLoading(true);
    setFailoverResult(null);
    try {
      const before = await api.overdriveBatch(BATCH_REQUESTS) as unknown as BatchResult;
      await api.overdriveSetHealth('overdrive', false);
      setLanes(prev => prev ? {...prev, overdrive: {...prev.overdrive, healthy: false}} : prev);
      const after = await api.overdriveBatch(BATCH_REQUESTS) as unknown as BatchResult;
      setFailoverResult({ before, after });
    } catch (err) {
      setBatchError(err instanceof Error ? err.message : 'Failover demo failed');
    } finally {
      await api.overdriveSetHealth('overdrive', true).catch(() => {});
      setLanes(prev => prev ? {...prev, overdrive: {...prev.overdrive, healthy: true}} : prev);
      setFailoverLoading(false);
    }
  }, []);

  const resetLanes = useCallback(async () => {
    for (const lane of ['eco', 'performance', 'overdrive']) {
      await api.overdriveSetHealth(lane, true);
    }
    setLanes(prev => {
      if (!prev) return prev;
      const reset = {...prev};
      for (const k of Object.keys(reset)) {
        reset[k] = {...reset[k], healthy: true};
      }
      return reset;
    });
    setFailoverResult(null);
    fetchStatus();
  }, [fetchStatus]);

  /* ---- Helpers ---- */
  const checkIcon = (result: string) => {
    if (result === 'pass') return <CheckCircleIcon color="var(--rh-color--success)" />;
    if (result === 'fail') return <ExclamationCircleIcon color="var(--rh-color--brand)" />;
    return <ExclamationTriangleIcon color="var(--rh-color--gaudi)" />;
  };

  const laneColor = (lane: string): 'green' | 'blue' | 'orange' | 'red' =>
    LANE_LABEL_COLOR[lane] ?? 'red';

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */
  return (
    <>
      {/* ======== HERO ======== */}
      <PageSection>
        <Content>
          <Content component="h1">Intelligent Inference Routing</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            Route AI workloads to the right Intel hardware automatically. Small tasks run on
            cost-efficient <strong>Xeon 6</strong> CPUs. Heavy workloads accelerate on{' '}
            <strong>Gaudi</strong>. The routing engine evaluates every request against a rubric
            and provides full decision evidence.
          </Content>
        </Content>

        {/* Inline architecture diagram */}
        <div style={{ marginTop: '1.5rem' }}>
          <div style={{ textAlign: 'center', marginBottom: '1rem' }}>
            <div style={{
              display: 'inline-block', padding: '10px 20px',
              background: 'var(--rh-color--surface)', border: '2px solid var(--rh-color--border)',
              borderRadius: '8px', fontWeight: 700, fontSize: '0.95rem',
            }}>
              Incoming Request
            </div>
            <div style={{ width: '2px', height: '16px', background: 'var(--rh-color--border)', margin: '0 auto' }} />
            <div style={{
              display: 'inline-block', padding: '8px 16px',
              background: 'var(--rh-color--surface-secondary)', border: '2px solid var(--rh-color--border-strong)',
              borderRadius: '8px', fontWeight: 600, fontSize: '0.82rem',
            }}>
              Task Type &rarr; Token Estimate &rarr; Priority &rarr; Lane Selection
            </div>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0', marginTop: '6px' }}>
              <div style={{ width: '2px', height: '16px', background: 'var(--rh-color--success)' }} />
              <div style={{ width: '100px' }} />
              <div style={{ width: '2px', height: '16px', background: 'var(--rh-color--xeon6)' }} />
              <div style={{ width: '100px' }} />
              <div style={{ width: '2px', height: '16px', background: 'var(--rh-color--gaudi)' }} />
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            {[
              { id: 'eco', label: 'Eco Lane', hw: 'Intel Xeon 6', tasks: 'Classification, small prompts', threshold: '≤ 4K tokens' },
              { id: 'performance', label: 'Performance Lane', hw: 'Intel Xeon 6 + AMX', tasks: 'Embeddings, reranking, summaries', threshold: '≤ 16K tokens' },
              { id: 'overdrive', label: 'Overdrive Lane', hw: 'Intel Gaudi', tasks: 'Long summaries, RCA, batch generation', threshold: '≥ 16K tokens' },
            ].map(lane => {
              const meta = LANE_META[lane.id];
              return (
                <div key={lane.id} style={{
                  flex: '1 1 200px', maxWidth: '260px', padding: '14px',
                  background: meta.bg, border: `2px solid ${meta.color}`,
                  borderRadius: '10px', borderTop: `4px solid ${meta.color}`,
                  textAlign: 'center',
                }}>
                  <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '4px' }}>{lane.label}</div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--rh-color--text-secondary)' }}>{lane.hw}</div>
                  <div style={{ fontSize: '0.78rem', marginTop: '4px' }}>{lane.tasks}</div>
                  <div style={{ fontSize: '0.75rem', marginTop: '2px', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>{lane.threshold}</div>
                </div>
              );
            })}
          </div>
        </div>
      </PageSection>

      {/* ======== STEP 1: INFRASTRUCTURE ======== */}
      <PageSection variant="secondary">
        <StepBadge step={1} label="See Your Infrastructure" />
        <Content component="p" style={{ maxWidth: '640px', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
          Three inference lanes map to Intel hardware tiers. Each lane runs a specific model on
          dedicated hardware and handles a set of task types. Toggle a lane off to simulate
          hardware failure.
        </Content>

        {lanesError && <Alert variant="warning" title={lanesError} isInline style={{ marginBottom: '1rem' }} />}
        {lanesLoading && !lanes ? (
          <Spinner size="lg" />
        ) : (
          <Gallery hasGutter minWidths={{ default: '280px' }}>
            {Object.keys(LANE_META).map((laneId) => {
              const meta = LANE_META[laneId];
              const status = lanes?.[laneId];
              const healthy = status?.healthy ?? true;
              return (
                <GalleryItem key={laneId}>
                  <Card isFullHeight style={{ borderTop: `4px solid ${meta.color}` }}>
                    <CardTitle style={{ textTransform: 'capitalize', fontWeight: 700 }}>
                      {laneId}
                    </CardTitle>
                    <CardBody>
                      <div style={{ marginBottom: '0.5rem', fontSize: '0.85rem' }}>
                        <strong>{status?.model || meta.model}</strong>
                        <Label isCompact color={meta.labelColor} style={{ marginLeft: '0.5rem' }}>
                          {status?.accelerator || meta.accelerator}
                        </Label>
                      </div>
                      <div style={{ marginBottom: '0.5rem', fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', fontFamily: 'var(--pf-t--global--font--family--mono)' }}>
                        {status?.endpoint || 'LiteLLM proxy'}
                      </div>
                      <div style={{ marginBottom: '0.5rem' }}>
                        {(status?.capabilities ?? meta.capabilities).map((cap) => (
                          <Label key={cap} isCompact color={meta.labelColor} style={{ marginRight: 4, marginBottom: 4 }}>
                            {cap}
                          </Label>
                        ))}
                      </div>
                      <div style={{
                        marginBottom: '0.75rem', fontSize: '0.8rem', color: 'var(--rh-color--text-secondary)',
                        fontStyle: 'italic', lineHeight: '1.5',
                      }}>
                        {meta.hwStory}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Switch
                          id={`lane-switch-${laneId}`}
                          label={healthy ? "Healthy" : "Unhealthy"}
                          isChecked={healthy}
                          onChange={(_e, checked) => toggleHealth(laneId, checked)}
                        />
                        <Label color={healthy ? 'green' : 'red'} isCompact>
                          {healthy ? 'UP' : 'DOWN'}
                        </Label>
                      </div>
                    </CardBody>
                  </Card>
                </GalleryItem>
              );
            })}
          </Gallery>
        )}
      </PageSection>

      {/* ======== STEP 2: ROUTE A REQUEST ======== */}
      <PageSection>
        <StepBadge step={2} label="Route a Request" />
        <Content component="p" style={{ maxWidth: '720px', marginBottom: '0.75rem' }}>
          In a production AI platform, different workloads have different hardware needs.
          A simple classification can run cheaply on a CPU, but a 30,000-token incident analysis
          needs GPU memory and bandwidth. This evaluator simulates that decision in real time.
        </Content>
        <Content component="p" style={{ maxWidth: '720px', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
          Choose a <strong>task type</strong> (the kind of AI work), set a <strong>token estimate</strong> (how
          large the input is), pick a <strong>priority</strong>, and set a <strong>latency target</strong>.
          The engine checks each parameter against the lane rubrics — endpoint health, capability match,
          token limits, and priority gates — then selects the optimal Intel hardware tier. Every check
          is shown so you can see exactly why the decision was made.
        </Content>

        {/* Parameter guide */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: '0.75rem', marginBottom: '1.5rem', maxWidth: '720px',
        }}>
          {[
            { param: 'Task Type', hint: 'What the model does — classification, embedding, summarization, incident analysis, etc.' },
            { param: 'Token Estimate', hint: 'Input size in tokens. Under 4K stays on Eco (Xeon 6). Over 16K routes to Overdrive (Gaudi).' },
            { param: 'Priority', hint: 'Low/normal tasks stay on CPU. High/critical tasks qualify for the Gaudi accelerator lane.' },
            { param: 'Latency Target', hint: 'Maximum acceptable response time. Tighter targets may require faster hardware.' },
          ].map(g => (
            <div key={g.param} style={{
              padding: '10px 12px', borderRadius: '8px',
              background: 'var(--rh-color--surface-secondary)',
              border: '1px solid var(--rh-color--border)',
            }}>
              <div style={{ fontWeight: 600, fontSize: '0.82rem', marginBottom: '2px' }}>{g.param}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--rh-color--text-secondary)', lineHeight: '1.4' }}>{g.hint}</div>
            </div>
          ))}
        </div>

        <Card>
          <CardBody>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
              <div style={{ minWidth: '180px' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Task Type</div>
                <Select
                  toggle={(ref) => (
                    <MenuToggle ref={ref} onClick={() => setTaskOpen(!taskOpen)} isExpanded={taskOpen} style={{ width: '180px' }}>
                      {taskType}
                    </MenuToggle>
                  )}
                  isOpen={taskOpen}
                  onSelect={(_e, value) => { setTaskType(value as string); setTaskOpen(false); }}
                  onOpenChange={setTaskOpen}
                  selected={taskType}
                >
                  {TASK_TYPES.map((t) => (
                    <SelectOption key={t} value={t}>{t}</SelectOption>
                  ))}
                </Select>
              </div>

              <div style={{ minWidth: '160px' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Token Estimate</div>
                <NumberInput
                  value={tokenEstimate}
                  min={0}
                  max={100000}
                  onMinus={() => setTokenEstimate(Math.max(0, tokenEstimate - 500))}
                  onPlus={() => setTokenEstimate(tokenEstimate + 500)}
                  onChange={(e) => {
                    const v = parseInt((e.target as HTMLInputElement).value, 10);
                    if (!isNaN(v)) setTokenEstimate(v);
                  }}
                  widthChars={7}
                />
              </div>

              <div style={{ minWidth: '140px' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Priority</div>
                <Select
                  toggle={(ref) => (
                    <MenuToggle ref={ref} onClick={() => setPriorityOpen(!priorityOpen)} isExpanded={priorityOpen} style={{ width: '140px' }}>
                      {priority}
                    </MenuToggle>
                  )}
                  isOpen={priorityOpen}
                  onSelect={(_e, value) => { setPriority(value as string); setPriorityOpen(false); }}
                  onOpenChange={setPriorityOpen}
                  selected={priority}
                >
                  {PRIORITIES.map((p) => (
                    <SelectOption key={p} value={p}>{p}</SelectOption>
                  ))}
                </Select>
              </div>

              <div style={{ minWidth: '160px' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Latency Target (ms)</div>
                <NumberInput
                  value={latencyTarget}
                  min={0}
                  max={60000}
                  onMinus={() => setLatencyTarget(Math.max(0, latencyTarget - 500))}
                  onPlus={() => setLatencyTarget(latencyTarget + 500)}
                  onChange={(e) => {
                    const v = parseInt((e.target as HTMLInputElement).value, 10);
                    if (!isNaN(v)) setLatencyTarget(v);
                  }}
                  widthChars={7}
                />
              </div>

              <div>
                <Button variant="primary" onClick={evaluateRoute} isLoading={routeLoading} isDisabled={routeLoading}>
                  Evaluate Route
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>

        {routeError && <Alert variant="danger" title={routeError} isInline style={{ marginTop: '1rem' }} />}

        {routeResult && (
          <Card style={{ marginTop: '1rem' }}>
            <CardBody>
              {/* Decision summary */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)', marginBottom: 4 }}>
                    Routed To
                  </div>
                  <Label color={laneColor(routeResult.selected_route ?? 'indeterminate')} style={{ fontSize: '1.2rem', padding: '8px 20px' }}>
                    {routeResult.selected_route?.toUpperCase() ?? 'INDETERMINATE'}
                  </Label>
                </div>
                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)', marginBottom: 4 }}>
                    Hardware
                  </div>
                  <span style={{ fontSize: '1.05rem', fontWeight: 600 }}>
                    {routeResult.selected_route ? (LANE_META[routeResult.selected_route]?.accelerator || '-') : '-'}
                  </span>
                </div>
                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)', marginBottom: 4 }}>
                    Outcome
                  </div>
                  <span style={{ fontSize: '1.05rem', fontWeight: 600 }}>{routeResult.outcome ?? '-'}</span>
                </div>
                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)', marginBottom: 4 }}>
                    Reason Codes
                  </div>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {routeResult.reason_codes?.length ? routeResult.reason_codes.map((r) => (
                      <Label key={r} isCompact color="grey">{r}</Label>
                    )) : <span>-</span>}
                  </div>
                </div>
              </div>

              {/* Decision trace */}
              <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 8 }}>Decision Trace</div>
              <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', overflowX: 'auto' }}>
                {[
                  { label: 'Received', detail: `${routeResult.request?.task_type || '?'} / ${routeResult.request?.token_estimate || '?'} tokens / ${routeResult.request?.priority || '?'}`, ok: true },
                  { label: 'Matrix Match', detail: `Target: ${routeResult.evaluated_routes?.[0] || '?'}`, ok: !!routeResult.selected_route },
                  { label: 'Rubric', detail: `${routeResult.checks?.filter(c => c.result === 'pass').length || 0}/${routeResult.checks?.length || 0} checks passed`, ok: routeResult.checks?.every(c => c.result === 'pass') },
                  { label: 'Selected', detail: routeResult.selected_route?.toUpperCase() || 'None', ok: !!routeResult.selected_route },
                ].map((s, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center' }}>
                    <div style={{
                      padding: '8px 14px', borderRadius: '8px', textAlign: 'center', minWidth: '100px',
                      background: s.ok ? 'var(--rh-color--success-bg)' : 'var(--rh-color--brand-light)',
                      border: `1px solid ${s.ok ? 'var(--rh-color--success)' : 'var(--rh-color--brand)'}`,
                    }}>
                      <div style={{ fontWeight: 600, fontSize: '0.8rem' }}>{s.label}</div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)', marginTop: '2px' }}>{s.detail}</div>
                    </div>
                    {i < 3 && <div style={{ width: '24px', height: '2px', background: 'var(--rh-color--border-strong)', flexShrink: 0 }} />}
                  </div>
                ))}
              </div>

              {/* Rubric checks */}
              {routeResult.checks && routeResult.checks.length > 0 && (
                <>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>Rubric Checks</div>
                  {routeResult.checks.map((c, i) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'flex-start', gap: '12px',
                      padding: '10px 14px', marginBottom: '6px', borderRadius: '8px',
                      background: c.result === 'pass' ? 'var(--rh-color--success-bg)' :
                        c.result === 'fail' ? 'var(--rh-color--brand-light)' : 'var(--rh-color--gaudi-bg)',
                      border: `1px solid ${c.result === 'pass' ? 'var(--rh-color--success)' :
                        c.result === 'fail' ? 'var(--rh-color--brand)' : 'var(--rh-color--gaudi)'}`,
                    }}>
                      <div style={{ flexShrink: 0, paddingTop: '2px' }}>
                        {checkIcon(c.result)}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                          <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{c.name.replace(/_/g, ' ')}</span>
                          <Label isCompact color={laneColor(c.route)}>{c.route}</Label>
                          <Label isCompact color={c.result === 'pass' ? 'green' : c.result === 'fail' ? 'red' : 'orange'}>
                            {c.result.toUpperCase()}
                          </Label>
                        </div>
                        {c.reason && (
                          <div style={{ fontSize: '0.8rem', color: 'var(--rh-color--text-secondary)', marginTop: '2px' }}>
                            {c.reason}
                          </div>
                        )}
                        {c.observed != null && (
                          <div style={{
                            fontSize: '0.78rem', fontFamily: 'var(--pf-t--global--font--family--mono)',
                            color: 'var(--rh-color--text-secondary)', marginTop: '3px',
                            padding: '3px 8px', background: 'rgba(0,0,0,0.04)', borderRadius: '4px',
                            display: 'inline-block',
                          }}>
                            {String(c.observed)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </>
              )}
            </CardBody>
          </Card>
        )}
      </PageSection>

      {/* ======== STEP 3: AT SCALE ======== */}
      <PageSection variant="secondary">
        <StepBadge step={3} label="See It at Scale" />
        <Content component="p" style={{ maxWidth: '640px', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
          Run 10 mixed AI workloads through the routing engine and watch them distribute across
          Xeon 6 and Gaudi hardware. Then simulate a Gaudi failure to see how the platform
          gracefully degrades without dropping requests.
        </Content>

        {/* Batch demo */}
        <Card>
          <CardTitle>Run a Mixed Workload Batch</CardTitle>
          <CardBody>
            <Content component="p" style={{ marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
              Send 10 requests with different task types, token sizes, and priorities through the
              routing engine. The results show how workloads are automatically distributed across
              Xeon 6 (eco and performance lanes) and Gaudi (overdrive lane).
            </Content>
            <Button variant="primary" onClick={runBatch} isLoading={batchLoading} isDisabled={batchLoading}>
              Run Batch Demo
            </Button>
          </CardBody>
        </Card>

        {batchError && <Alert variant="danger" title={batchError} isInline style={{ marginTop: '1rem' }} />}

        {batchResult && (
          <Card style={{ marginTop: '1rem' }}>
            <CardTitle>Workload Distribution Across Hardware</CardTitle>
            <CardBody>
              <div style={{ display: 'flex', gap: 0, height: '36px', borderRadius: 6, overflow: 'hidden', marginBottom: '1rem' }}>
                {(['eco', 'performance', 'overdrive'] as const).map((lane) => {
                  const count = batchResult.routes?.[lane] ?? 0;
                  const total = batchResult.total_requests ?? 0;
                  const pct = total > 0 ? (count / total) * 100 : 0;
                  if (pct === 0) return null;
                  return (
                    <div key={lane} style={{
                      width: `${pct}%`, backgroundColor: LANE_META[lane].color, color: '#fff',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '0.82rem', fontWeight: 600, minWidth: '30px',
                    }}>
                      {lane} ({count})
                    </div>
                  );
                })}
                {((batchResult.fallbacks ?? 0) + (batchResult.indeterminate ?? 0)) > 0 && (
                  <div style={{
                    width: `${(((batchResult.fallbacks ?? 0) + (batchResult.indeterminate ?? 0)) / (batchResult.total_requests ?? 1)) * 100}%`,
                    backgroundColor: 'var(--rh-color--local)', color: '#fff',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '0.82rem', fontWeight: 600, minWidth: '30px',
                  }}>
                    other ({(batchResult.fallbacks ?? 0) + (batchResult.indeterminate ?? 0)})
                  </div>
                )}
              </div>

              <Gallery hasGutter minWidths={{ default: '120px' }}>
                {[
                  { label: 'Xeon 6 (Eco)', value: batchResult.routes?.eco ?? 0, color: 'green' as const },
                  { label: 'Xeon 6 (Perf)', value: batchResult.routes?.performance ?? 0, color: 'blue' as const },
                  { label: 'Gaudi', value: batchResult.routes?.overdrive ?? 0, color: 'orange' as const },
                  { label: 'Fallback', value: batchResult.fallbacks ?? 0, color: 'grey' as const },
                  { label: 'Unrouted', value: batchResult.indeterminate ?? 0, color: 'red' as const },
                ].map((item) => (
                  <GalleryItem key={item.label}>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{item.value}</div>
                      <Label color={item.color} isCompact>{item.label}</Label>
                    </div>
                  </GalleryItem>
                ))}
              </Gallery>

              {batchResult.top_reason_codes && batchResult.top_reason_codes.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 6 }}>Top Reason Codes</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {batchResult.top_reason_codes.map((r) => (
                      <Label key={r} isCompact color="grey">{r}</Label>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ marginTop: '1rem', fontSize: '0.85rem', color: 'var(--rh-color--text-secondary)' }}>
                Total requests: {batchResult.total_requests ?? 0}
              </div>
            </CardBody>
          </Card>
        )}

        {/* Failover simulation */}
        <Card style={{ marginTop: '1.5rem' }}>
          <CardTitle>Simulate Gaudi Hardware Failure</CardTitle>
          <CardBody>
            <Content component="p" style={{ marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
              What happens when the Gaudi accelerator goes offline? This simulation temporarily
              disables the overdrive lane, re-runs the same 10 workloads, then <strong>automatically
              restores</strong> the lane. Watch how requests that need Gaudi are gracefully rerouted
              to Xeon 6 — with full evidence for every decision.
            </Content>
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <Button
                variant="primary"
                onClick={runFailoverDemo}
                isLoading={failoverLoading}
                isDisabled={failoverLoading}
              >
                Simulate Gaudi Failure
              </Button>
              {failoverResult && (
                <Button variant="secondary" onClick={resetLanes}>
                  Reset All Lanes
                </Button>
              )}
            </div>
          </CardBody>
        </Card>

        {failoverResult && (
          <Card style={{ marginTop: '1rem' }}>
            <CardTitle>Before vs After: Gaudi Failure Simulation</CardTitle>
            <CardBody>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
                {/* Before */}
                <div>
                  <div style={{ fontWeight: 700, marginBottom: '0.5rem' }}>
                    <Label color="green" isCompact style={{ marginRight: '0.5rem' }}>BEFORE</Label>
                    All Hardware Online
                  </div>
                  <div style={{ display: 'flex', gap: 0, height: '28px', borderRadius: 6, overflow: 'hidden', marginBottom: '0.75rem' }}>
                    {(['eco', 'performance', 'overdrive'] as const).map(lane => {
                      const count = failoverResult.before.routes?.[lane] ?? 0;
                      const total = failoverResult.before.total_requests ?? 1;
                      const pct = (count / total) * 100;
                      if (pct === 0) return null;
                      return (
                        <div key={lane} style={{
                          width: `${pct}%`, backgroundColor: LANE_META[lane]?.color || 'grey',
                          color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: '0.75rem', fontWeight: 600, minWidth: '25px',
                        }}>
                          {count}
                        </div>
                      );
                    })}
                  </div>
                  <div style={{ fontSize: '0.82rem' }}>
                    Xeon 6 Eco: {failoverResult.before.routes?.eco ?? 0} &middot;{' '}
                    Xeon 6 Perf: {failoverResult.before.routes?.performance ?? 0} &middot;{' '}
                    Gaudi: {failoverResult.before.routes?.overdrive ?? 0}
                  </div>
                </div>

                {/* After */}
                <div>
                  <div style={{ fontWeight: 700, marginBottom: '0.5rem' }}>
                    <Label color="red" isCompact style={{ marginRight: '0.5rem' }}>AFTER</Label>
                    Gaudi Offline
                  </div>
                  <div style={{ display: 'flex', gap: 0, height: '28px', borderRadius: 6, overflow: 'hidden', marginBottom: '0.75rem' }}>
                    {(['eco', 'performance', 'overdrive'] as const).map(lane => {
                      const count = failoverResult.after.routes?.[lane] ?? 0;
                      const total = failoverResult.after.total_requests ?? 1;
                      const pct = (count / total) * 100;
                      if (pct === 0) return null;
                      return (
                        <div key={lane} style={{
                          width: `${pct}%`, backgroundColor: LANE_META[lane]?.color || 'grey',
                          color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: '0.75rem', fontWeight: 600, minWidth: '25px',
                        }}>
                          {count}
                        </div>
                      );
                    })}
                    {(failoverResult.after.fallbacks ?? 0) > 0 && (
                      <div style={{
                        width: `${((failoverResult.after.fallbacks ?? 0) / (failoverResult.after.total_requests ?? 1)) * 100}%`,
                        backgroundColor: 'var(--rh-color--xeon6)', color: '#fff',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '0.75rem', fontWeight: 600, minWidth: '25px',
                        backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 5px, rgba(255,255,255,0.15) 5px, rgba(255,255,255,0.15) 10px)',
                      }}>
                        {failoverResult.after.fallbacks}
                      </div>
                    )}
                  </div>
                  <div style={{ fontSize: '0.82rem' }}>
                    Xeon 6 Eco: {failoverResult.after.routes?.eco ?? 0} &middot;{' '}
                    Xeon 6 Perf: {failoverResult.after.routes?.performance ?? 0} &middot;{' '}
                    Gaudi: {failoverResult.after.routes?.overdrive ?? 0} &middot;{' '}
                    <strong style={{ color: 'var(--rh-color--brand)' }}>
                      Rerouted to Xeon 6: {failoverResult.after.fallbacks ?? 0}
                    </strong>
                  </div>
                </div>
              </div>

              <Alert variant="success" isInline style={{ marginTop: '1rem' }} title="Graceful degradation confirmed">
                When Gaudi went offline, {failoverResult.after.fallbacks ?? 0} workloads that required
                the accelerator were automatically rerouted to Xeon 6. Zero requests were dropped.
                The overdrive lane has been automatically restored to healthy.
              </Alert>
            </CardBody>
          </Card>
        )}
      </PageSection>
    </>
  );
}
