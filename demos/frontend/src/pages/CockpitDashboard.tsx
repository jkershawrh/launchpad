import { useState, useEffect, useRef, useReducer } from 'react';
import { api } from '../api/client';
import '../styles/cockpit.css';

/* ─── Config ─── */
const WORKLOAD_DEMOS = [
  { id: 'incident_storm', name: 'Incident Storm', desc: 'Enterprise alert flood — classify on Xeon 6, deep analysis on Gaudi.', phases: ['Alert Triage (Xeon 6)', 'Knowledge Search (Xeon 6)', 'Deep Analysis (Gaudi)', 'Batch Reporting (Gaudi)'] },
  { id: 'rag_barrage', name: 'RAG Barrage', desc: 'High-throughput RAG — embed, search, rerank, answer generation.', phases: ['Document Indexing (Xeon 6)', 'Relevance Scoring (Xeon 6)', 'Answer Generation (Mixed)', 'Document Distillation (Gaudi)'] },
  { id: 'token_cannon', name: 'Token Cannon', desc: 'Maximum generation throughput — stress Gaudi with heavy output.', phases: ['Long Analysis (Gaudi)', 'Batch Reports (Gaudi)', 'Doc Distillation (Gaudi)', 'Code Review (Gaudi)'] },
  { id: 'model_race', name: 'Model Race', desc: 'Same tasks across all hardware — compare Xeon 6 vs Gaudi live.', phases: ['Small Tasks (Xeon Eco)', 'Mid Tasks (Xeon Perf)', 'Large Tasks (Gaudi)'] },
  { id: 'dashboard_storm', name: 'Dashboard Storm', desc: 'Multimodal — operational screenshots classified and interpreted.', phases: ['Screenshot Classify (Xeon 6)', 'Chart Interpret (Gaudi)', 'Summary Generation (Gaudi)', 'Incident Synthesis (Gaudi)'] },
  { id: 'multimodal_incident_commander', name: 'Incident Commander', desc: 'Multimodal — screenshots + logs + metrics into incident synthesis.', phases: ['Screenshot Classify (Xeon 6)', 'Diagram Analysis (Gaudi)', 'Incident Synthesis (Gaudi)'] },
  { id: 'architecture_explainer', name: 'Architecture Explainer', desc: 'Multimodal — diagrams explained with vision-language reasoning.', phases: ['Diagram Classify (Xeon 6)', 'Diagram Explain (Gaudi)', 'Architecture Summary (Gaudi)'] },
  { id: 'visual_rag_barrage', name: 'Visual RAG', desc: 'Multimodal — embed images, search visually, answer with context.', phases: ['Image Embedding (Xeon 6)', 'Visual Rerank (Xeon 6)', 'Image Q&A (Gaudi)'] },
  { id: 'token_cannon_multimodal', name: 'Token Cannon MM', desc: 'Multimodal — stress heavy visual generation across Gaudi.', phases: ['Chart Interpretation (Gaudi)', 'Doc Explanation (Gaudi)', 'Visual Summary (Gaudi)'] },
  { id: 'image_to_manual', name: 'Image to Manual', desc: 'Multimodal — generate installation guides from equipment images.', phases: ['Image Classify (Xeon 6)', 'Manual Generation (Gaudi)', 'Doc Distillation (Gaudi)'] },
];
const SWARM_DEMOS = [
  { id: 'swarm:incident', name: 'Swarm: Incident', desc: 'Multi-agent incident investigation across Xeon 6 + Gaudi.', phases: ['Wave 1: Investigation', 'Wave 2: Root Cause', 'Wave 3: Report'] },
  { id: 'swarm:security_audit', name: 'Swarm: Security Audit', desc: 'Multi-agent security scan — CVEs, compliance, threat analysis.', phases: ['Wave 1: Scanning', 'Wave 2: Risk Assessment', 'Wave 3: Audit Report'] },
  { id: 'swarm:capacity_planning', name: 'Swarm: Capacity Plan', desc: 'Multi-agent capacity analysis — utilization, growth, cost.', phases: ['Wave 1: Data Collection', 'Wave 2: Cost Optimization', 'Wave 3: Report'] },
];
const DEMOS = [...WORKLOAD_DEMOS, ...SWARM_DEMOS];
const SCALES = [
  { id: 'quick', label: 'Quick', mode: 'standby', count: 5, time: '~5s', locked: false },
  { id: 'standard', label: 'Standard', mode: 'drive', count: 25, time: '~20s', locked: false },
  { id: 'extended', label: 'Extended', mode: 'boost', count: 250, time: '~3 min', locked: true },
];
const MODEL_COLORS: Record<string, string> = { 'granite-4-0-h-tiny': '#3e8635', 'codellama-7b-instruct': '#0068b5', 'llama-scout-17b': '#e67e22' };

/* ─── State Machine ─── */
interface Snapshot { t: number; completed: number; eco: number; perf: number; gaudi: number; }

interface CockpitState {
  phase: 'idle' | 'running' | 'done';
  runId: string | null;
  demoId: string | null;
  completed: number;
  total: number;
  routes: Record<string, number>;
  rps: number;
  tps: number;
  p95: number;
  images: number;
  models: Record<string, Record<string, unknown>>;
  history: Snapshot[];
  startTime: number;
}

type Action =
  | { type: 'LAUNCH'; demoId: string; runId: string }
  | { type: 'POLL'; completed: number; total: number; routes: Record<string, number>; rps: number; tps: number; p95: number; images: number; models: Record<string, Record<string, unknown>>; elapsed: number }
  | { type: 'COMPLETE'; completed: number; routes: Record<string, number>; rps: number; tps: number; p95: number; images: number; models: Record<string, Record<string, unknown>> }
  | { type: 'RESET' };

const INITIAL: CockpitState = {
  phase: 'idle', runId: null, demoId: null,
  completed: 0, total: 0, routes: {}, rps: 0, tps: 0, p95: 0, images: 0,
  models: {}, history: [], startTime: 0,
};

function reducer(state: CockpitState, action: Action): CockpitState {
  switch (action.type) {
    case 'LAUNCH':
      return { ...INITIAL, phase: 'running', runId: action.runId, demoId: action.demoId, startTime: Date.now() };

    case 'POLL': {
      if (state.phase !== 'running') return state;
      // Only climb — never let values drop within a run
      const completed = Math.max(state.completed, action.completed);
      const total = Math.max(state.total, action.total);
      const routes: Record<string, number> = { ...state.routes };
      for (const [k, v] of Object.entries(action.routes)) routes[k] = Math.max(routes[k] || 0, v);
      const rps = Math.max(state.rps, action.rps);
      const tps = Math.max(state.tps, action.tps);
      const p95 = Math.max(state.p95, action.p95);
      const images = Math.max(state.images, action.images);
      // Models: only update if count increased
      const models = { ...state.models };
      for (const [k, v] of Object.entries(action.models)) {
        if (!models[k] || (v.count as number) >= ((models[k].count as number) || 0)) models[k] = v;
      }
      // History: add snapshot if completed changed
      let history = state.history;
      const lastSnap = history[history.length - 1];
      if (!lastSnap || lastSnap.completed < completed) {
        history = [...history, { t: action.elapsed, completed, eco: routes.eco || 0, perf: routes.performance || 0, gaudi: routes.overdrive || 0 }];
      }
      return { ...state, completed, total, routes, rps, tps, p95, images, models, history };
    }

    case 'COMPLETE': {
      // Final values from latest_completed — set directly (not max'd, these are authoritative)
      const routes = Object.keys(action.routes).length > 0 ? action.routes : state.routes;
      const completed = action.completed || state.completed;
      return { ...state, phase: 'done', completed, routes, rps: action.rps || state.rps, tps: action.tps || state.tps, p95: action.p95 || state.p95, images: action.images || state.images, models: Object.keys(action.models).length > 0 ? action.models : state.models };
    }

    case 'RESET':
      return INITIAL;

    default:
      return state;
  }
}

/* ─── Component ─── */
export default function CockpitDashboard() {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const [scale, setScale] = useState('standard');
  const [unlockCode, setUnlockCode] = useState('');
  const [launching, setLaunching] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const selectedScale = SCALES.find(s => s.id === scale) || SCALES[1];
  const demoMeta = DEMOS.find(d => d.id === state.demoId);

  // Poll only during RUNNING
  useEffect(() => {
    if (state.phase !== 'running' || !state.runId) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }

    const poll = async () => {
      try {
        const d = await api.platformStatus() as Record<string, unknown>;
        const lp = d.live_progress as { completed: number; total: number } | null;
        const agg = d.aggregate as Record<string, unknown> | undefined;
        const rc = (agg?.route_counts || {}) as Record<string, number>;
        const mt = (d.model_telemetry || {}) as Record<string, Record<string, unknown>>;
        const activeRuns = d.active_runs as Array<Record<string, unknown>> | undefined;
        const isSwarm = state.demoId?.startsWith('swarm:');
        const isActive = activeRuns && activeRuns.some(r => isSwarm ? r.type === 'swarm' : r.type === 'workload');

        // Check if our run completed
        const lc = isSwarm ? d.swarm_completed as Record<string, unknown> | null : d.latest_completed as Record<string, unknown> | null;
        if (!isActive && lc && lc.run_id === state.runId) {
          if (isSwarm) {
            dispatch({
              type: 'COMPLETE',
              completed: lc.agent_count as number || 0,
              routes: (lc.route_counts || {}) as Record<string, number>,
              rps: 0, tps: 0, p95: Math.round(lc.total_ms as number || 0),
              images: 0, models: {},
            });
          } else {
            dispatch({
              type: 'COMPLETE',
              completed: lc.total_requests as number || 0,
              routes: (lc.route_counts || {}) as Record<string, number>,
              rps: Math.round(lc.requests_per_second as number || 0),
              tps: Math.round(lc.estimated_tokens_per_second as number || 0),
              p95: Math.round(lc.p95_latency_ms as number || 0),
              images: lc.total_images as number || 0,
              models: mt,
            });
          }
          return;
        }

        // Still running — update with climbing values
        if (isSwarm) {
          const swarmRun = activeRuns?.find(r => r.type === 'swarm');
          if (swarmRun) {
            const elapsed = Math.round((Date.now() - state.startTime) / 1000);
            dispatch({
              type: 'POLL',
              completed: swarmRun.agents_done as number || 0,
              total: swarmRun.agents_total as number || 0,
              routes: rc, rps: 0, tps: 0, p95: 0, images: 0, models: {},
              elapsed,
            });
          }
        } else if (lp && lp.completed > 0) {
          const elapsed = Math.round((Date.now() - state.startTime) / 1000);
          dispatch({
            type: 'POLL',
            completed: lp.completed, total: lp.total,
            routes: rc,
            rps: Math.round(agg?.requests_per_second as number || 0),
            tps: Math.round(agg?.estimated_tokens_per_second as number || 0),
            p95: Math.round(agg?.p95_latency_ms as number || 0),
            images: agg?.total_images as number || 0,
            models: mt,
            elapsed,
          });
        }
      } catch { /* ignore */ }
    };

    pollRef.current = setInterval(poll, 1200);
    poll();
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [state.phase, state.runId, state.startTime]);

  const launchDemo = async (demoId: string) => {
    const sc = SCALES.find(s => s.id === scale) || SCALES[1];
    setLaunching(true);
    try {
      let resp: { run_id?: string };
      if (demoId.startsWith('swarm:')) {
        const scenario = demoId.replace('swarm:', '');
        const swarmDepth = sc.id === 'quick' ? 'triage' : sc.id === 'extended' ? 'deep' : 'full';
        resp = await api.swarmRun(scenario, 42, swarmDepth) as { run_id?: string };
      } else {
        resp = await api.workloadRun(demoId, sc.mode, 42, true, sc.locked ? unlockCode : '') as { run_id?: string };
      }
      if (resp.run_id) {
        dispatch({ type: 'LAUNCH', demoId, runId: resp.run_id });
      }
    } catch { /* ignore — stay idle */ }
    setLaunching(false);
  };

  const { phase, completed, total, routes, rps, tps, p95, images, models, history } = state;
  const eco = routes.eco || 0;
  const perf = routes.performance || 0;
  const gaudi = routes.overdrive || 0;
  const totalReqs = eco + perf + gaudi;
  const pct = total > 0 ? Math.round(completed / total * 100) : 0;
  const isActive = phase === 'running' || phase === 'done';

  return (
    <div className="cockpit" style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <img src="/intel-logo.svg" alt="Intel" style={{ height: '20px', opacity: 0.9 }} />
          <img src="/redhat-logo.svg" alt="Red Hat" style={{ height: '20px', opacity: 0.9 }} />
          <div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, letterSpacing: '0.05em' }}>
              INFERENCE <span style={{ color: '#ee0000' }}>OVERDRIVE</span>
            </div>
            <div style={{ fontSize: '0.65rem', color: '#666', letterSpacing: '0.04em' }}>INTEL XEON 6 + GAUDI · LIVE INFERENCE</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {isActive && (
            <div style={{ padding: '6px 16px', borderRadius: '4px', fontSize: '0.78rem', fontWeight: 700, letterSpacing: '0.08em',
              background: phase === 'done' ? '#3e8635' : '#0068b5', color: '#fff', transition: 'background 0.5s' }}>
              {phase === 'done' ? 'COMPLETE' : 'LIVE'}
            </div>
          )}
          {phase === 'done' && (
            <button className="ck-mode-btn" onClick={() => dispatch({ type: 'RESET' })} style={{ fontSize: '0.72rem', padding: '5px 12px' }}>← Back</button>
          )}
        </div>
      </div>

      {/* ─── IDLE ─── */}
      {phase === 'idle' && (
        <>
          <div style={{ textAlign: 'center', margin: '32px 0 12px', color: '#ccc', fontSize: '0.95rem', fontWeight: 600 }}>Select a demo</div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginBottom: '16px', alignItems: 'center' }}>
            <div style={{ fontSize: '0.68rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Scale:</div>
            <div className="ck-select">
              {SCALES.map(s => (
                <button key={s.id} className={scale === s.id ? 'active' : ''} onClick={() => setScale(s.id)}>
                  {s.label} ({s.count}) · {s.time}
                </button>
              ))}
            </div>
          </div>
          {selectedScale.locked && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginBottom: '12px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.68rem', color: '#666' }}>Unlock:</span>
              <input type="password" value={unlockCode} onChange={e => setUnlockCode(e.target.value)} placeholder="Required"
                style={{ background: '#1e1e1e', border: '1px solid #333', borderRadius: '4px', padding: '4px 10px', color: '#ccc', fontSize: '0.78rem', width: '140px', fontFamily: 'RedHatMono, monospace' }} />
            </div>
          )}
          <div style={{ textAlign: 'center', marginBottom: '20px', fontSize: '0.7rem', color: '#555' }}>
            Live · {selectedScale.count} requests · {selectedScale.time}
          </div>
          {[
            { label: 'TEXT WORKLOADS', demos: WORKLOAD_DEMOS.slice(0, 4) },
            { label: 'MULTIMODAL WORKLOADS', demos: WORKLOAD_DEMOS.slice(4) },
            { label: 'AGENT SWARMS', demos: SWARM_DEMOS },
          ].map(section => (
            <div key={section.label}>
              <div style={{ fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.08em', color: '#555', margin: '12px 0 6px', textTransform: 'uppercase' }}>{section.label}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '10px', marginBottom: '8px' }}>
                {section.demos.map(d => {
                  const disabled = launching || (selectedScale.locked && !unlockCode);
                  return (
                    <div key={d.id} onClick={() => !disabled && launchDemo(d.id)}
                      className="ck-card" style={{ opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}>
                      <div style={{ fontWeight: 700, fontSize: '0.88rem', marginBottom: '4px' }}>{d.name}</div>
                      <div style={{ fontSize: '0.75rem', color: '#888' }}>{d.desc}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </>
      )}

      {/* ─── RUNNING + DONE (persistent layout) ─── */}
      {isActive && demoMeta && (
        <>
          {/* Demo header + progress */}
          <div style={{ background: '#161616', border: `1px solid ${phase === 'done' ? '#3e8635' : '#333'}`, borderRadius: '6px', padding: '16px', marginBottom: '14px', transition: 'border-color 0.5s' }}>
            <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '2px' }}>{demoMeta.name}</div>
            <div style={{ fontSize: '0.78rem', color: '#888', marginBottom: '10px' }}>{demoMeta.desc}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: '4px' }}>
              <span style={{ fontFamily: 'RedHatMono, monospace', fontWeight: 700 }}>{completed} / {total || '...'}</span>
              <span style={{ color: phase === 'done' ? '#3e8635' : '#0068b5', fontWeight: 700 }}>{phase === 'done' ? 'DONE' : `${pct}%`}</span>
            </div>
            <div style={{ height: '6px', borderRadius: '3px', background: '#2a2a2a', overflow: 'hidden' }}>
              <div className="ck-smooth" style={{ height: '100%', width: `${pct}%`, background: phase === 'done' ? '#3e8635' : '#0068b5', borderRadius: '3px' }} />
            </div>
          </div>

          {/* Phases */}
          <div style={{ marginBottom: '14px' }}>
            {demoMeta.phases.map((ph, i) => {
              const threshold = ((i + 1) / demoMeta.phases.length) * 100;
              const done = pct >= threshold;
              const active = !done && pct >= (i / demoMeta.phases.length) * 100;
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '4px 0', fontSize: '0.82rem' }}>
                  <div style={{ width: '18px', height: '18px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.65rem', fontWeight: 700,
                    background: done ? '#3e8635' : active ? '#0068b5' : '#2a2a2a', color: '#fff', flexShrink: 0, transition: 'background 0.3s' }}>
                    {done ? '✓' : active ? '▶' : '○'}
                  </div>
                  <span style={{ color: done ? '#3e8635' : active ? '#e8e8e8' : '#555', transition: 'color 0.3s' }}>{ph}</span>
                </div>
              );
            })}
          </div>

          {/* Stats bar — always visible */}
          <div style={{ display: 'flex', gap: '14px', marginBottom: '14px', padding: '10px 14px', background: '#161616', border: '1px solid #333', borderRadius: '6px', flexWrap: 'wrap' }}>
            {[
              { v: rps, l: 'req/s' }, { v: tps.toLocaleString(), l: 'tok/s' },
              { v: p95, l: 'ms p95' }, { v: images, l: 'images' },
            ].map(m => (
              <span key={m.l}><span style={{ fontFamily: 'RedHatMono, monospace', fontWeight: 700, fontSize: '1rem', color: (typeof m.v === 'number' ? m.v : parseInt(String(m.v))) > 0 ? '#e8e8e8' : '#444' }}>{m.v}</span> <span style={{ color: '#888', fontSize: '0.78rem' }}>{m.l}</span></span>
            ))}
          </div>

          {/* Timeline chart */}
          {history.length > 0 && (
            <div style={{ background: '#161616', border: '1px solid #333', borderRadius: '6px', padding: '12px', marginBottom: '14px' }}>
              <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#888', marginBottom: '6px' }}>
                {phase === 'done' ? 'Run Timeline' : 'Requests Over Time'}
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1px', height: '50px' }}>
                {history.map((s, i) => {
                  const max = Math.max(...history.map(x => x.completed)) || 1;
                  return (
                    <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
                      {s.gaudi > 0 && <div style={{ height: `${(s.gaudi / max) * 100}%`, background: '#e67e22', borderRadius: '1px 1px 0 0', minHeight: '2px' }} />}
                      {s.perf > 0 && <div style={{ height: `${(s.perf / max) * 100}%`, background: '#0068b5', minHeight: '2px' }} />}
                      {s.eco > 0 && <div style={{ height: `${(s.eco / max) * 100}%`, background: '#3e8635', borderRadius: '0 0 1px 1px', minHeight: '2px' }} />}
                    </div>
                  );
                })}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: '#555', marginTop: '3px' }}>
                <span>0s</span>
                <span style={{ display: 'flex', gap: '8px' }}><span style={{ color: '#3e8635' }}>● Eco</span><span style={{ color: '#0068b5' }}>● Perf</span><span style={{ color: '#e67e22' }}>● Gaudi</span></span>
                <span>{history[history.length - 1]?.t || 0}s</span>
              </div>
            </div>
          )}

          {/* Lane cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginBottom: '14px' }}>
            {[
              { name: 'INTEL XEON ECO', hw: 'Granite · Xeon 6', count: eco, color: '#3e8635' },
              { name: 'INTEL XEON PERF', hw: 'CodeLlama · Xeon 6 + AMX', count: perf, color: '#0068b5' },
              { name: 'INTEL GAUDI', hw: 'Llama Scout 17B', count: gaudi, color: '#e67e22' },
            ].map(l => (
              <div key={l.name} style={{ background: '#161616', border: `1px solid ${l.count > 0 ? l.color : '#333'}`, borderRadius: '6px', padding: '10px', borderLeft: `3px solid ${l.color}`, transition: 'border-color 0.3s' }}>
                <div style={{ fontWeight: 700, fontSize: '0.72rem', letterSpacing: '0.04em' }}>{l.name}</div>
                <div style={{ fontSize: '0.6rem', color: '#888' }}>{l.hw}</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, fontFamily: 'RedHatMono, monospace', color: l.count > 0 ? l.color : '#444', marginTop: '4px' }}>
                  {l.count} <span style={{ fontSize: '0.68rem', color: '#888' }}>({totalReqs > 0 ? Math.round(l.count / totalReqs * 100) : 0}%)</span>
                </div>
              </div>
            ))}
          </div>

          {/* Model activity — always visible */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#888', marginBottom: '6px' }}>MODEL ACTIVITY</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
              {[
                { key: 'granite-4-0-h-tiny', name: 'Granite', hw: 'Xeon 6 Eco' },
                { key: 'codellama-7b-instruct', name: 'CodeLlama 7B', hw: 'Xeon 6 + AMX' },
                { key: 'llama-scout-17b', name: 'Llama Scout 17B', hw: 'Gaudi' },
              ].map(m => {
                const s = models[m.key];
                const count = s ? s.count as number : 0;
                const active = count > 0;
                return (
                  <div key={m.key} style={{ background: '#161616', border: `1px solid ${active ? MODEL_COLORS[m.key] : '#333'}`, borderRadius: '6px', padding: '8px', opacity: active ? 1 : 0.4, transition: 'all 0.4s' }}>
                    <div style={{ fontWeight: 700, fontSize: '0.72rem', color: MODEL_COLORS[m.key] }}>{m.name}</div>
                    <div style={{ fontSize: '0.6rem', color: '#888' }}>{m.hw}</div>
                    <div style={{ fontSize: '0.72rem', marginTop: '3px' }}>
                      <b style={{ color: active ? '#e8e8e8' : '#444' }}>{count}</b> <span style={{ color: '#888' }}>reqs</span>
                      {s && <span style={{ marginLeft: '8px' }}><b style={{ color: MODEL_COLORS[m.key] }}>{(s.tokens_per_sec as number || 0).toLocaleString()}</b> <span style={{ color: '#888' }}>tok/s</span></span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Actions */}
          {phase === 'done' && (
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="ck-mode-btn" onClick={() => state.demoId && launchDemo(state.demoId)}>Run Again</button>
              <button className="ck-mode-btn" onClick={() => dispatch({ type: 'RESET' })}>Try Another</button>
            </div>
          )}
        </>
      )}

      <div style={{ marginTop: '24px', fontSize: '0.6rem', color: '#444', textAlign: 'center' }}>Intel Xeon 6 + Gaudi — Red Hat OpenShift AI</div>
    </div>
  );
}
