import { useState, useCallback } from 'react';
import {
  Alert,
  Button,
  Card,
  CardBody,
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
  TextInput,
} from '@patternfly/react-core';
import { api } from '../api/client';

const PROFILES = [
  { value: 'incident_storm', label: 'Incident Storm', desc: 'Enterprise incident flood — classification, triage, RCA, batch reporting' },
  { value: 'rag_barrage', label: 'RAG Barrage', desc: 'High-throughput RAG — embed, search, rerank, answer generation' },
  { value: 'token_cannon', label: 'Token Cannon', desc: 'Maximize generated tokens — heavy generation across all lanes' },
  { value: 'model_race', label: 'Model Race', desc: 'Cross-hardware comparison — comparable workloads for reporting' },
  { value: 'dashboard_storm', label: 'Dashboard Storm', desc: 'Multimodal — operational screenshots classified, summarized, interpreted' },
  { value: 'multimodal_incident_commander', label: 'Incident Commander', desc: 'Multimodal — screenshots + logs + metrics into incident synthesis' },
  { value: 'architecture_explainer', label: 'Architecture Explainer', desc: 'Multimodal — diagrams explained with vision-language reasoning' },
  { value: 'visual_rag_barrage', label: 'Visual RAG', desc: 'Multimodal — embed images, search visually, answer with context' },
  { value: 'token_cannon_multimodal', label: 'Token Cannon MM', desc: 'Multimodal — stress heavy visual generation across Gaudi' },
  { value: 'image_to_manual', label: 'Image to Manual', desc: 'Multimodal — generate installation guides and manuals from equipment images' },
];

const NARRATIVES: Record<string, { title: string; story: string; phases: Array<{ name: string; tasks: string[]; hw: string; desc: string }> }> = {
  incident_storm: {
    title: 'Enterprise Incident Storm',
    story: 'A production AI platform is under pressure. Alerts are flooding in — pod crashes, memory pressure, certificate expiry, and Gaudi accelerator overload. The platform must triage every alert (Xeon 6), find relevant runbooks (Xeon 6), generate root cause analysis (Gaudi), and produce executive summaries — all simultaneously.',
    phases: [
      { name: 'Alert Triage', tasks: ['classification'], hw: 'Xeon 6', desc: 'Incoming alerts classified by severity on Xeon 6 — fast, cheap, no GPU needed.' },
      { name: 'Knowledge Retrieval', tasks: ['embedding', 'rerank'], hw: 'Xeon 6', desc: 'Alert text embedded and matched against runbooks using Xeon 6 with AMX.' },
      { name: 'Situation Summary', tasks: ['short_summary'], hw: 'Xeon 6', desc: 'Quick executive briefs generated on Xeon 6 for the ops dashboard.' },
      { name: 'Deep Analysis', tasks: ['long_summary', 'incident_rca'], hw: 'Gaudi', desc: 'Root cause analysis on Gaudi — needs memory bandwidth for large context.' },
      { name: 'Overnight Report', tasks: ['batch_summary'], hw: 'Gaudi', desc: 'Batch reports with capacity planning recommendations on Gaudi.' },
    ],
  },
  rag_barrage: {
    title: 'High-Throughput RAG Pipeline',
    story: 'An enterprise knowledge base is being queried at scale. Engineers are asking questions about Intel hardware, OpenShift deployment, and model optimization. Every question triggers an embed-search-rerank-generate pipeline spanning Xeon 6 and Gaudi.',
    phases: [
      { name: 'Document Indexing', tasks: ['embedding'], hw: 'Xeon 6', desc: 'Knowledge base articles vectorized on Xeon 6 for fast indexing.' },
      { name: 'Relevance Scoring', tasks: ['rerank'], hw: 'Xeon 6', desc: 'Retrieved docs re-ranked by CodeLlama cross-encoder on Xeon 6.' },
      { name: 'Answer Generation', tasks: ['rag_question'], hw: 'Mixed', desc: 'Simple questions on Xeon 6. Complex synthesis routed to Gaudi.' },
      { name: 'Document Distillation', tasks: ['document_summary'], hw: 'Gaudi', desc: 'Long technical docs condensed on Gaudi high-bandwidth memory.' },
    ],
  },
  token_cannon: {
    title: 'Maximum Generation Throughput',
    story: 'Stress test with the heaviest generation workloads — long analyses, batch reports, document distillation, and codebase reviews. Nearly everything routes to Gaudi because these tasks demand large context windows and sustained generation.',
    phases: [
      { name: 'Long Analysis', tasks: ['long_summary'], hw: 'Gaudi', desc: 'Multi-page analyses at 100+ tokens/sec on Gaudi.' },
      { name: 'Batch Reports', tasks: ['batch_summary'], hw: 'Gaudi', desc: 'Weekly telemetry aggregated into comprehensive reports.' },
      { name: 'Document Distillation', tasks: ['document_summary'], hw: 'Gaudi', desc: '40+ page whitepapers condensed using full context window.' },
      { name: 'Code Review', tasks: ['code_summary'], hw: 'Gaudi', desc: 'Codebase analysis and optimization recommendations.' },
    ],
  },
  model_race: {
    title: 'Cross-Hardware Comparison',
    story: 'Same task types run across all three tiers to show why hardware-aware routing matters. Small tasks prove Xeon 6 is faster and cheaper. Large tasks prove Gaudi is essential.',
    phases: [
      { name: 'Small → Eco', tasks: ['classification'], hw: 'Xeon 6 Eco', desc: 'Quick classification on Granite — fast, minimal cost.' },
      { name: 'Mid → Performance', tasks: ['short_summary'], hw: 'Xeon 6 Perf', desc: 'Summaries on CodeLlama 7B with AMX — no GPU cost.' },
      { name: 'Large → Overdrive', tasks: ['long_summary', 'document_summary'], hw: 'Gaudi', desc: 'Heavy generation — only viable on Gaudi HBM.' },
    ],
  },
  dashboard_storm: {
    title: 'Dashboard Storm (Multimodal)',
    story: 'Operational dashboards flood the platform with screenshots. Xeon 6 classifies and sorts them instantly. Gaudi explains high-value screenshots using vision-language reasoning.',
    phases: [
      { name: 'Screenshot Classify', tasks: ['screenshot_classification'], hw: 'Xeon 6 Eco', desc: 'Quick classification of dashboard type and alert state.' },
      { name: 'Chart Interpret', tasks: ['chart_interpretation'], hw: 'Gaudi', desc: 'Vision-language interpretation of time-series charts.' },
      { name: 'Screenshot Summary', tasks: ['screenshot_summary'], hw: 'Gaudi', desc: 'Full dashboard explanation with anomaly detection.' },
      { name: 'Incident Synthesis', tasks: ['multimodal_incident_summary'], hw: 'Gaudi', desc: 'Multi-screenshot incident summary with visual evidence.' },
    ],
  },
  multimodal_incident_commander: {
    title: 'Incident Commander (Multimodal)',
    story: 'A production incident unfolds. Screenshots, logs, and metrics pour in. Xeon 6 classifies fast. Gaudi synthesizes everything into root cause analysis using vision and text.',
    phases: [
      { name: 'Visual Triage', tasks: ['screenshot_summary', 'chart_interpretation'], hw: 'Gaudi', desc: 'Dashboard screenshots analyzed for anomalies.' },
      { name: 'Root Cause', tasks: ['multimodal_rca'], hw: 'Gaudi', desc: 'Multi-source RCA combining screenshots, diagrams, and logs.' },
      { name: 'Document Review', tasks: ['document_visual_summary'], hw: 'Gaudi', desc: 'Post-mortem documents with charts summarized.' },
    ],
  },
  architecture_explainer: {
    title: 'Architecture Explainer (Multimodal)',
    story: 'Architecture diagrams submitted for AI-powered explanation. Gaudi handles vision-language reasoning to interpret complex system diagrams and answer questions.',
    phases: [
      { name: 'Diagram Explain', tasks: ['diagram_explanation'], hw: 'Gaudi', desc: 'Architecture diagrams interpreted with system understanding.' },
      { name: 'Visual Q&A', tasks: ['visual_rag_question'], hw: 'Gaudi', desc: 'Questions answered using diagrams + documentation context.' },
    ],
  },
  visual_rag_barrage: {
    title: 'Visual RAG (Multimodal)',
    story: 'Multimodal knowledge base queried at scale. Documents with images, diagrams, and screenshots are indexed on Xeon 6 and answered on Gaudi.',
    phases: [
      { name: 'Visual Index', tasks: ['image_text_embedding', 'visual_similarity'], hw: 'Xeon 6', desc: 'Images and text embedded for multimodal search.' },
      { name: 'Layout Extract', tasks: ['ocr_layout_extract'], hw: 'Xeon 6', desc: 'Text and structure extracted from document pages.' },
      { name: 'Visual Answer', tasks: ['visual_rag_question', 'document_visual_summary'], hw: 'Gaudi', desc: 'Answers synthesized from visual + text context.' },
    ],
  },
  token_cannon_multimodal: {
    title: 'Token Cannon: Multimodal',
    story: 'Maximum multimodal generation. Nearly everything routes to Gaudi — vision-language reasoning with large context windows across screenshots, charts, and documents.',
    phases: [
      { name: 'Heavy Visual Gen', tasks: ['screenshot_summary', 'chart_interpretation', 'document_visual_summary', 'multimodal_rca'], hw: 'Gaudi', desc: 'All heavy multimodal generation on Gaudi HBM.' },
    ],
  },
  image_to_manual: {
    title: 'Image to Manual (Multimodal)',
    story: 'Product images and equipment photos are submitted. Xeon 6 identifies the hardware. Gaudi generates complete installation guides, operating manuals, and troubleshooting docs from a single image.',
    phases: [
      { name: 'Image Identify', tasks: ['image_classification'], hw: 'Xeon 6 Eco', desc: 'Identify hardware type from the image — server, accelerator, switch.' },
      { name: 'Manual Generate', tasks: ['image_to_manual'], hw: 'Gaudi', desc: 'Generate full technical documentation from the equipment image.' },
      { name: 'Config Capture', tasks: ['screenshot_summary'], hw: 'Gaudi', desc: 'Capture configuration details from management interface screenshots.' },
    ],
  },
};

const MODES = [
  { value: 'standby', label: 'Standby (5)', desc: '5 requests — quick sanity check' },
  { value: 'drive', label: 'Drive (25)', desc: '25 requests — standard demo' },
  { value: 'boost', label: 'Boost (250)', desc: '250 requests — stress test' },
  { value: 'overdrive', label: 'Overdrive (1,000)', desc: '1,000 requests — full power' },
  { value: 'max_q', label: 'Max Q (custom)', desc: 'Custom request count' },
];

const LANE_COLORS: Record<string, string> = {
  eco: 'var(--rh-color--success)',
  performance: 'var(--rh-color--xeon6)',
  overdrive: 'var(--rh-color--gaudi)',
  unrouted: 'var(--rh-color--local)',
};

const LANE_LABELS: Record<string, { label: string; color: 'green' | 'blue' | 'orange' | 'grey' }> = {
  eco: { label: 'Xeon 6 (Eco)', color: 'green' },
  performance: { label: 'Xeon 6 (Perf)', color: 'blue' },
  overdrive: { label: 'Gaudi', color: 'orange' },
  unrouted: { label: 'Unrouted', color: 'grey' },
};

interface RunResult {
  run_id: string;
  workload_profile: string;
  power_mode: string;
  total_requests: number;
  completed_requests: number;
  route_counts: Record<string, number>;
  total_input_tokens_estimate: number;
  total_output_tokens_estimate: number;
  requests_per_second: number;
  estimated_tokens_per_second: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  xeon_eco_utilization_pct: number;
  xeon_performance_utilization_pct: number;
  gaudi_overdrive_utilization_pct: number;
  report_md: string;
  mode_label: string;
}

export default function WorkloadDemo() {
  const [profile, setProfile] = useState('incident_storm');
  const [profileOpen, setProfileOpen] = useState(false);
  const [mode, setMode] = useState('drive');
  const [modeOpen, setModeOpen] = useState(false);
  const [seed, setSeed] = useState(42);
  const [liveMode, setLiveMode] = useState(false);
  const [unlockCode, setUnlockCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<RunResult | null>(null);

  const GOVERNED = new Set(['boost', 'overdrive', 'max_q']);
  const needsUnlock = liveMode && GOVERNED.has(mode);

  const [progress, setProgress] = useState<{ completed: number; total: number; results: Array<{ lane: string; task_type: string; latency_ms: number; prompt?: string; hw?: string; routing_reason?: string; outcome?: string; image_url?: string; image_title?: string; modality?: string }> } | null>(null);
  const [expandedRequest, setExpandedRequest] = useState<number | null>(null);
  const [expandedPhaseFilter, setExpandedPhaseFilter] = useState<string | null>(null);

  const runWorkload = useCallback(async () => {
    setLoading(true);
    setError('');
    setResult(null);
    setProgress(null);
    try {
      const startResp = await api.workloadRun(profile, mode, seed, liveMode, unlockCode) as { run_id: string };
      const runId = startResp.run_id;

      const poll = async () => {
        for (let i = 0; i < 600; i++) {
          await new Promise(r => setTimeout(r, 1000));
          try {
            const status = await api.workloadStatus(runId) as Record<string, unknown>;
            setProgress({
              completed: (status.completed as number) || 0,
              total: (status.total as number) || 0,
              results: (status.results as Array<{ lane: string; task_type: string; latency_ms: number; prompt?: string }>) || [],
            });
            if (status.status === 'complete') {
              setResult(status as unknown as RunResult);
              return;
            }
            if (status.status === 'error') {
              setError((status.error as string) || 'Run failed');
              return;
            }
          } catch {
            // poll failed, retry
          }
        }
        setError('Run timed out');
      };
      await poll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Workload run failed');
    } finally {
      setLoading(false);
    }
  }, [profile, mode, seed, liveMode, unlockCode]);

  const profileMeta = PROFILES.find(p => p.value === profile);

  return (
    <>
      <PageSection>
        <Content>
          <Content component="h1">Workload Performance Demo</Content>
          <Content component="p" style={{ maxWidth: '780px', fontSize: '1.05rem' }}>
            Run real enterprise workload scenarios at different scales. Watch how requests
            distribute across Intel Xeon 6 (fast, cheap tasks) and Gaudi (heavy generation).
            Each profile simulates a pattern you'd see in production — incident response,
            RAG pipelines, heavy generation, or cross-hardware comparison.
          </Content>
        </Content>
      </PageSection>

      {/* Controls */}
      <PageSection variant="secondary">
        <Content component="h2" style={{ marginBottom: '0.75rem' }}>Configure Run</Content>
        <Card>
          <CardBody>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'flex-end' }}>
              <div style={{ minWidth: '220px' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Workload Profile</div>
                <Select
                  toggle={(ref) => (
                    <MenuToggle ref={ref} onClick={() => setProfileOpen(!profileOpen)} isExpanded={profileOpen} style={{ width: '220px' }}>
                      {profileMeta?.label || profile}
                    </MenuToggle>
                  )}
                  isOpen={profileOpen}
                  onSelect={(_e, value) => { setProfile(value as string); setProfileOpen(false); }}
                  onOpenChange={setProfileOpen}
                  selected={profile}
                >
                  {PROFILES.map(p => (
                    <SelectOption key={p.value} value={p.value} description={p.desc}>{p.label}</SelectOption>
                  ))}
                </Select>
              </div>

              <div style={{ minWidth: '200px' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Power Mode</div>
                <Select
                  toggle={(ref) => (
                    <MenuToggle ref={ref} onClick={() => setModeOpen(!modeOpen)} isExpanded={modeOpen} style={{ width: '200px' }}>
                      {MODES.find(m => m.value === mode)?.label || mode}
                    </MenuToggle>
                  )}
                  isOpen={modeOpen}
                  onSelect={(_e, value) => { setMode(value as string); setModeOpen(false); }}
                  onOpenChange={setModeOpen}
                  selected={mode}
                >
                  {MODES.map(m => (
                    <SelectOption key={m.value} value={m.value} description={m.desc}>{m.label}</SelectOption>
                  ))}
                </Select>
              </div>

              <div style={{ minWidth: '120px' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 4 }}>Seed</div>
                <NumberInput
                  value={seed}
                  min={0}
                  max={999999}
                  onMinus={() => setSeed(Math.max(0, seed - 1))}
                  onPlus={() => setSeed(seed + 1)}
                  onChange={(e) => {
                    const v = parseInt((e.target as HTMLInputElement).value, 10);
                    if (!isNaN(v)) setSeed(v);
                  }}
                  widthChars={6}
                />
              </div>

              <div>
                <Button variant="primary" onClick={runWorkload} isLoading={loading} isDisabled={loading || (needsUnlock && !unlockCode)}>
                  {liveMode ? 'Run Live' : 'Run Simulated'}
                </Button>
              </div>
            </div>

            {/* Live mode controls */}
            <div style={{ marginTop: '1rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              <Switch
                id="live-mode-toggle"
                label={liveMode ? 'Live Mode' : 'Simulated'}
                isChecked={liveMode}
                onChange={(_e, checked) => setLiveMode(checked)}
              />
              {liveMode && (
                <Label color="orange" isCompact>Real inference calls to LiteLLM — throttled to 80 RPM</Label>
              )}
              {needsUnlock && (
                <TextInput
                  type="password"
                  value={unlockCode}
                  onChange={(_e, val) => setUnlockCode(val)}
                  placeholder="Unlock code required"
                  aria-label="Unlock code"
                  style={{ maxWidth: '200px' }}
                />
              )}
            </div>

            {liveMode && (
              <Alert variant="warning" isInline style={{ marginTop: '0.75rem' }} title="Live mode active">
                Requests will be sent to the LiteLLM backend at ~80 requests/minute.
                {GOVERNED.has(mode) && !unlockCode && ' This power mode requires an unlock code.'}
                {mode === 'drive' && ' Estimated time: ~20 seconds.'}
                {mode === 'boost' && ' Estimated time: ~3 minutes.'}
                {mode === 'overdrive' && ' Estimated time: ~12 minutes.'}
              </Alert>
            )}

            {/* Scenario narrative */}
            {NARRATIVES[profile] && (
              <div style={{ marginTop: '1.25rem' }}>
                <div style={{
                  padding: '16px', borderRadius: '8px',
                  background: 'var(--rh-color--surface-secondary)', border: '1px solid var(--rh-color--border)',
                }}>
                  <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '6px' }}>
                    {NARRATIVES[profile].title}
                  </div>
                  <div style={{ fontSize: '0.88rem', lineHeight: '1.6', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
                    {NARRATIVES[profile].story}
                  </div>
                  <div style={{ display: 'flex', gap: '0', flexWrap: 'wrap' }}>
                    {NARRATIVES[profile].phases.map((phase, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center' }}>
                        <div style={{
                          padding: '8px 12px', borderRadius: '6px', minWidth: '120px',
                          background: phase.hw.includes('Gaudi') ? 'var(--rh-color--gaudi-bg)' : 'var(--rh-color--xeon6-bg)',
                          border: `1px solid ${phase.hw.includes('Gaudi') ? 'var(--rh-color--gaudi)' : 'var(--rh-color--xeon6)'}`,
                        }}>
                          <div style={{ fontWeight: 600, fontSize: '0.8rem' }}>{phase.name}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--rh-color--text-secondary)', marginTop: '2px' }}>
                            {phase.hw}
                          </div>
                        </div>
                        {i < NARRATIVES[profile].phases.length - 1 && (
                          <div style={{ width: '20px', height: '2px', background: 'var(--rh-color--border-strong)', flexShrink: 0 }} />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </PageSection>

      {error && (
        <PageSection>
          <Alert variant="danger" title={error} isInline />
        </PageSection>
      )}

      {loading && progress && (
        <PageSection>
          <Content component="h2" style={{ marginBottom: '0.75rem' }}>Live Feed</Content>

          {/* Progress bar */}
          <div style={{ marginBottom: '1rem', maxWidth: '700px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '0.85rem' }}>
              <span style={{ fontWeight: 600 }}>
                {progress.completed} / {progress.total} requests
              </span>
              <span style={{ color: 'var(--rh-color--text-secondary)' }}>
                {progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0}%
              </span>
            </div>
            <div style={{ height: '12px', borderRadius: '6px', overflow: 'hidden', background: 'var(--rh-color--surface-secondary)' }}>
              <div style={{
                height: '100%', borderRadius: '6px', transition: 'width 0.3s',
                width: `${progress.total > 0 ? (progress.completed / progress.total) * 100 : 0}%`,
                background: liveMode ? 'var(--rh-color--gaudi)' : 'var(--rh-color--xeon6)',
              }} />
            </div>
          </div>

          {/* Live route counts */}
          {progress.results.length > 0 && (() => {
            const counts: Record<string, number> = {};
            for (const r of progress.results) {
              counts[r.lane] = (counts[r.lane] || 0) + 1;
            }
            return (
              <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                {Object.entries(counts).map(([lane, count]) => (
                  <div key={lane} style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{count}</div>
                    <Label color={LANE_LABELS[lane]?.color || 'grey'} isCompact>{LANE_LABELS[lane]?.label || lane}</Label>
                  </div>
                ))}
              </div>
            );
          })()}

          {/* Active phase indicator */}
          {NARRATIVES[profile] && (() => {
            const lastResult = progress.results[progress.results.length - 1];
            const activePhase = lastResult
              ? NARRATIVES[profile].phases.find(p => p.tasks.includes(lastResult.task_type))
              : NARRATIVES[profile].phases[0];
            return activePhase ? (
              <div style={{
                marginBottom: '1rem', padding: '10px 14px', borderRadius: '6px',
                background: activePhase.hw.includes('Gaudi') ? 'var(--rh-color--gaudi-bg)' : 'var(--rh-color--xeon6-bg)',
                border: `1px solid ${activePhase.hw.includes('Gaudi') ? 'var(--rh-color--gaudi)' : 'var(--rh-color--xeon6)'}`,
              }}>
                <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>{activePhase.name}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--rh-color--text-secondary)' }}>{activePhase.desc}</div>
              </div>
            ) : null;
          })()}

          {/* Live request log (last 10) */}
          <div style={{
            maxHeight: '500px', overflowY: 'auto', borderRadius: '6px',
            border: '1px solid var(--rh-color--border)', background: 'var(--rh-color--surface)',
          }}>
            {progress.results.slice(-10).reverse().map((r, idx) => {
              const globalIdx = progress.results.length - 10 + idx;
              const isExpanded = expandedRequest === globalIdx;
              return (
                <div key={idx}
                  style={{
                    padding: '10px 12px', borderBottom: '1px solid var(--rh-color--border)',
                    cursor: 'pointer', transition: 'background 0.15s',
                    background: isExpanded ? 'var(--rh-color--surface-secondary)' : undefined,
                  }}
                  onClick={() => setExpandedRequest(isExpanded ? null : globalIdx)}
                >
                  {/* Header row */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{
                      width: '10px', height: '10px', borderRadius: '50%', flexShrink: 0,
                      background: LANE_COLORS[r.lane] || 'grey',
                    }} />
                    <span style={{ fontWeight: 600, fontSize: '0.85rem', minWidth: '110px' }}>{r.task_type}</span>
                    <Label isCompact color={LANE_LABELS[r.lane]?.color || 'grey'}>{r.hw || LANE_LABELS[r.lane]?.label || r.lane}</Label>
                    {r.outcome === 'fallback' && <Label isCompact color="orange">FALLBACK</Label>}
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--pf-t--global--font--family--mono)', fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)' }}>
                      {r.latency_ms?.toFixed(0)}ms
                    </span>
                  </div>

                  {/* Prompt preview (always visible) */}
                  {r.prompt && (
                    <div style={{
                      fontSize: '0.78rem', color: 'var(--pf-t--global--text--color--subtle)',
                      marginTop: '4px', marginLeft: '18px', lineHeight: '1.4',
                      ...(isExpanded ? {} : { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '600px' }),
                    }}>
                      {r.prompt}
                    </div>
                  )}

                  {/* Expanded: routing reasoning */}
                  {isExpanded && r.routing_reason && (
                    <div style={{
                      marginTop: '8px', marginLeft: '18px', padding: '8px 12px', borderRadius: '6px',
                      background: r.lane === 'overdrive' ? 'var(--rh-color--gaudi-bg)' : 'var(--rh-color--xeon6-bg)',
                      border: `1px solid ${r.lane === 'overdrive' ? 'var(--rh-color--gaudi)' : 'var(--rh-color--xeon6)'}`,
                      fontSize: '0.8rem', lineHeight: '1.5',
                    }}>
                      <div style={{ fontWeight: 600, marginBottom: '2px', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)' }}>
                        Why {r.hw || r.lane}?
                      </div>
                      {r.routing_reason}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </PageSection>
      )}

      {loading && !progress && (
        <PageSection>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <Spinner size="lg" />
            <span>Starting {profileMeta?.label || profile} in {mode} mode...</span>
          </div>
        </PageSection>
      )}

      {result && (
        <>
          {/* Route Distribution */}
          <PageSection>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem' }}>
              <Content component="h2" style={{ margin: 0 }}>Route Distribution</Content>
              <Label color={result.mode_label === 'live' ? 'orange' : 'blue'} isCompact style={{ fontSize: '0.85rem', padding: '4px 12px' }}>
                {(result.mode_label || 'simulated').toUpperCase()}
              </Label>
            </div>

            <div style={{ display: 'flex', gap: 0, height: '40px', borderRadius: 6, overflow: 'hidden', marginBottom: '1rem', maxWidth: '700px' }}>
              {Object.entries(result.route_counts).map(([lane, count]) => {
                const pct = (count / result.total_requests) * 100;
                if (pct === 0) return null;
                return (
                  <div key={lane} style={{
                    width: `${pct}%`, backgroundColor: LANE_COLORS[lane] || 'grey', color: '#fff',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '0.82rem', fontWeight: 600, minWidth: '30px',
                  }}>
                    {LANE_LABELS[lane]?.label || lane} ({count})
                  </div>
                );
              })}
            </div>

            <Gallery hasGutter minWidths={{ default: '140px' }}>
              {Object.entries(result.route_counts).map(([lane, count]) => {
                const meta = LANE_LABELS[lane];
                return (
                  <GalleryItem key={lane}>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '2rem', fontWeight: 700 }}>{count.toLocaleString()}</div>
                      <Label color={meta?.color || 'grey'} isCompact>{meta?.label || lane}</Label>
                    </div>
                  </GalleryItem>
                );
              })}
            </Gallery>
          </PageSection>

          {/* Performance Metrics */}
          <PageSection variant="secondary">
            <Content component="h2" style={{ marginBottom: '0.75rem' }}>Performance Metrics</Content>
            <Content component="p" style={{ marginBottom: '1rem', fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)' }}>
              Metrics are simulated using the mock timing provider. Values reflect realistic relative performance across Intel hardware tiers.
            </Content>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', maxWidth: '800px' }}>
              {[
                { label: 'Total Requests', value: result.total_requests.toLocaleString() },
                { label: 'Requests/sec', value: result.requests_per_second.toFixed(1) },
                { label: 'Est. Tokens/sec', value: result.estimated_tokens_per_second.toLocaleString(undefined, { maximumFractionDigits: 0 }) },
                { label: 'p50 Latency', value: `${result.p50_latency_ms.toFixed(0)} ms` },
                { label: 'p95 Latency', value: `${result.p95_latency_ms.toFixed(0)} ms` },
                { label: 'p99 Latency', value: `${result.p99_latency_ms.toFixed(0)} ms` },
                { label: 'Input Tokens', value: result.total_input_tokens_estimate.toLocaleString() },
                { label: 'Output Tokens', value: result.total_output_tokens_estimate.toLocaleString() },
              ].map(m => (
                <Card key={m.label}>
                  <CardBody style={{ textAlign: 'center', padding: '1rem' }}>
                    <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{m.value}</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', marginTop: '4px' }}>{m.label}</div>
                  </CardBody>
                </Card>
              ))}
            </div>
          </PageSection>

          {/* Utilization */}
          <PageSection>
            <Content component="h2" style={{ marginBottom: '0.75rem' }}>Hardware Utilization</Content>
            <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap', maxWidth: '700px' }}>
              {[
                { label: 'Xeon 6 Eco', pct: result.xeon_eco_utilization_pct, color: 'var(--rh-color--success)' },
                { label: 'Xeon 6 Performance', pct: result.xeon_performance_utilization_pct, color: 'var(--rh-color--xeon6)' },
                { label: 'Gaudi Overdrive', pct: result.gaudi_overdrive_utilization_pct, color: 'var(--rh-color--gaudi)' },
              ].map(u => (
                <div key={u.label} style={{ flex: '1 1 180px' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '6px' }}>{u.label}</div>
                  <div style={{
                    height: '24px', borderRadius: '4px', overflow: 'hidden',
                    background: 'var(--rh-color--surface-secondary)',
                  }}>
                    <div style={{
                      height: '100%', width: `${u.pct}%`, background: u.color,
                      borderRadius: '4px', transition: 'width 0.3s',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: '#fff', fontSize: '0.75rem', fontWeight: 600,
                      minWidth: u.pct > 5 ? '30px' : undefined,
                    }}>
                      {u.pct > 5 ? `${u.pct.toFixed(0)}%` : ''}
                    </div>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--rh-color--text-secondary)', marginTop: '4px' }}>
                    {u.pct.toFixed(1)}% of workload
                  </div>
                </div>
              ))}
            </div>
          </PageSection>

          {/* Run Info */}
          <PageSection variant="secondary">
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)' }}>
              <span><strong>Run ID:</strong> {result.run_id}</span>
              <span><strong>Profile:</strong> {result.workload_profile}</span>
              <span><strong>Mode:</strong> {result.power_mode}</span>
              <span><strong>Seed:</strong> {seed}</span>
            </div>
          </PageSection>
        </>
      )}

      {/* Request Detail Log — persists after run completes */}
      {progress && progress.results.length > 0 && !loading && (
        <PageSection>
          <Content component="h2" style={{ marginBottom: '0.5rem' }}>Request Detail Log</Content>
          <Content component="p" style={{ maxWidth: '640px', marginBottom: '1rem', color: 'var(--rh-color--text-secondary)' }}>
            Click any request to see the full scenario prompt and the routing engine's reasoning
            for selecting that Intel hardware tier.
          </Content>

          {/* Phase filter */}
          {NARRATIVES[profile] && (
            <div style={{ display: 'flex', gap: '6px', marginBottom: '1rem', flexWrap: 'wrap' }}>
              <Button variant={expandedPhaseFilter === null ? 'primary' : 'secondary'} size="sm"
                onClick={() => setExpandedPhaseFilter(null)}>All ({progress.results.length})</Button>
              {NARRATIVES[profile].phases.map(phase => {
                const count = progress.results.filter(r => phase.tasks.includes(r.task_type)).length;
                return count > 0 ? (
                  <Button key={phase.name} size="sm"
                    variant={expandedPhaseFilter === phase.name ? 'primary' : 'secondary'}
                    onClick={() => setExpandedPhaseFilter(expandedPhaseFilter === phase.name ? null : phase.name)}>
                    {phase.name} ({count})
                  </Button>
                ) : null;
              })}
            </div>
          )}

          <div style={{
            maxHeight: '600px', overflowY: 'auto', borderRadius: '6px',
            border: '1px solid var(--rh-color--border)', background: 'var(--rh-color--surface)',
          }}>
            {progress.results
              .filter(r => {
                if (!expandedPhaseFilter || !NARRATIVES[profile]) return true;
                const phase = NARRATIVES[profile].phases.find(p => p.name === expandedPhaseFilter);
                return phase ? phase.tasks.includes(r.task_type) : true;
              })
              .map((r, idx) => {
                const isExpanded = expandedRequest === idx;
                return (
                  <div key={idx}
                    style={{
                      padding: '10px 12px', borderBottom: '1px solid var(--rh-color--border)',
                      cursor: 'pointer', transition: 'background 0.15s',
                      background: isExpanded ? 'var(--rh-color--surface-secondary)' : undefined,
                    }}
                    onClick={() => setExpandedRequest(isExpanded ? null : idx)}
                  >
                    {/* Header */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{
                        width: '10px', height: '10px', borderRadius: '50%', flexShrink: 0,
                        background: LANE_COLORS[r.lane] || 'grey',
                      }} />
                      <span style={{ fontWeight: 600, fontSize: '0.85rem', minWidth: '110px' }}>{r.task_type}</span>
                      <Label isCompact color={LANE_LABELS[r.lane]?.color || 'grey'}>{r.hw || LANE_LABELS[r.lane]?.label || r.lane}</Label>
                      {r.outcome === 'fallback' && <Label isCompact color="orange">FALLBACK</Label>}
                      <span style={{ fontSize: '0.75rem', color: 'var(--rh-color--text-secondary)' }}>
                        #{idx + 1}
                      </span>
                      <span style={{ marginLeft: 'auto', fontFamily: 'var(--pf-t--global--font--family--mono)', fontSize: '0.82rem', color: 'var(--rh-color--text-secondary)' }}>
                        {r.latency_ms?.toFixed(0)}ms
                      </span>
                    </div>

                    {/* Prompt (collapsed = truncated, expanded = full) */}
                    {r.prompt && (
                      <div style={{
                        fontSize: '0.8rem', color: 'var(--pf-t--global--text--color--subtle)',
                        marginTop: '4px', marginLeft: '18px', lineHeight: '1.5',
                        ...(isExpanded ? {} : { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '700px' }),
                      }}>
                        {r.prompt}
                      </div>
                    )}

                    {/* Expanded detail */}
                    {isExpanded && (
                      <div style={{ marginTop: '10px', marginLeft: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {/* Image asset */}
                        {r.image_url && (
                          <div style={{
                            padding: '8px', borderRadius: '6px',
                            background: 'var(--rh-color--surface-secondary)', border: '1px solid var(--rh-color--border)',
                          }}>
                            <div style={{ fontWeight: 600, fontSize: '0.78rem', marginBottom: '6px', textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)' }}>
                              Input: {r.image_title || r.modality || 'Image'}
                            </div>
                            <img src={r.image_url} alt={r.image_title || 'Demo asset'} style={{
                              maxWidth: '100%', maxHeight: '200px', borderRadius: '4px',
                              border: '1px solid var(--rh-color--border)',
                            }} />
                          </div>
                        )}

                        {/* Routing reasoning */}
                        {r.routing_reason && (
                          <div style={{
                            padding: '10px 14px', borderRadius: '6px',
                            background: r.lane === 'overdrive' ? 'var(--rh-color--gaudi-bg)' : 'var(--rh-color--xeon6-bg)',
                            border: `1px solid ${r.lane === 'overdrive' ? 'var(--rh-color--gaudi)' : 'var(--rh-color--xeon6)'}`,
                            fontSize: '0.82rem', lineHeight: '1.5',
                          }}>
                            <div style={{ fontWeight: 700, marginBottom: '4px', fontSize: '0.78rem', textTransform: 'uppercase', color: 'var(--rh-color--text-secondary)' }}>
                              Why {r.hw || r.lane}?
                            </div>
                            {r.routing_reason}
                          </div>
                        )}

                        {/* Request metadata */}
                        <div style={{
                          padding: '8px 14px', borderRadius: '6px',
                          background: 'var(--rh-color--surface-secondary)', border: '1px solid var(--rh-color--border)',
                          fontSize: '0.78rem', display: 'flex', gap: '1.5rem', flexWrap: 'wrap',
                          fontFamily: 'var(--pf-t--global--font--family--mono)',
                        }}>
                          <span>tokens: {(r as Record<string, unknown>).input_tokens?.toLocaleString()}</span>
                          <span>output: {(r as Record<string, unknown>).output_tokens?.toLocaleString()}</span>
                          <span>latency: {r.latency_ms?.toFixed(1)}ms</span>
                          <span>outcome: {r.outcome}</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        </PageSection>
      )}
    </>
  );
}
