import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { AdminObservability, LifecycleHealth, ProvisioningObservation } from '../api/types';
import { clusterHealth, formatOperationalDuration, grafanaDrilldownUrl, modelHealth, seatHealth, type HealthAssessment, type OperationalTone } from '../observabilityContract';

type View = 'labs' | 'models' | 'clusters' | 'events';

const TONE_CLASSES: Record<OperationalTone, string> = {
  success: 'border-[#3E8635]/70 bg-[#17351f] text-[#9AD98D]',
  info: 'border-[#0071C5]/70 bg-[#102d43] text-[#8CCCF5]',
  warning: 'border-[#F0AB00]/70 bg-[#3a2d0b] text-[#F4C145]',
  danger: 'border-[#C9190B]/80 bg-[#3b1717] text-[#FF8A80]',
  muted: 'border-[#555]/70 bg-[#242424] text-[#B8BBBE]',
};

const DOT_CLASSES: Record<OperationalTone, string> = {
  success: 'bg-[#73BC63]', info: 'bg-[#73BCF7]', warning: 'bg-[#F4C145]', danger: 'bg-[#FA6868]', muted: 'bg-[#8A8D90]',
};

function Metric({ label, value, detail, tone = 'text-white' }: { label: string; value: string | number; detail: string; tone?: string }) {
  return <div className="rounded-lg border border-[#303030] bg-[#202020] px-4 py-3"><p className="text-[11px] font-bold uppercase tracking-wider text-[#8A8D90]">{label}</p><p className={`mt-1 text-xl font-bold ${tone}`}>{value}</p><p className="mt-0.5 text-xs text-[#8A8D90]">{detail}</p></div>;
}

function HealthLabel({ health }: { health: HealthAssessment }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-bold uppercase tracking-wide ${TONE_CLASSES[health.tone]}`}><span className={`h-2 w-2 rounded-full ${DOT_CLASSES[health.tone]}`} />{health.label}</span>;
}

function Legend() {
  return <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-[#8A8D90]" aria-label="Health legend">{([['success', 'Healthy'], ['warning', 'Watch'], ['danger', 'Critical'], ['muted', 'No signal']] as const).map(([tone, label]) => <span key={tone} className="inline-flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-sm ${DOT_CLASSES[tone]}`} />{label}</span>)}</div>;
}

function TabButton({ active, children, onClick }: { active: boolean; children: string; onClick: () => void }) {
  return <button role="tab" aria-selected={active} onClick={onClick} className={`border-b-2 px-5 py-3 text-sm font-semibold transition ${active ? 'border-[#EE0000] text-white' : 'border-transparent text-[#8A8D90] hover:text-white'}`}>{children}</button>;
}

function SeatGrid({ data, lab }: { data: AdminObservability; lab: ProvisioningObservation }) {
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">{lab.seats.map((seat) => {
    const traffic = seat.session_id ? data.llm.attribution.filter((row) => row.session_id === seat.session_id) : [];
    const health = seatHealth(seat, traffic);
    const requests = traffic.reduce((sum, row) => sum + row.requests, 0);
    const errors = traffic.reduce((sum, row) => sum + row.errors, 0);
    const tokens = traffic.reduce((sum, row) => sum + row.total_tokens, 0);
    const p95 = Math.max(0, ...traffic.map((row) => row.p95_latency_ms || 0));
    return <article key={`${lab.order_id}-${seat.seat_number}`} className={`flex min-h-[218px] flex-col rounded-lg border p-4 ${TONE_CLASSES[health.tone]}`}>
      <div className="flex items-start justify-between gap-2"><div><p className="text-lg font-bold text-white">Seat {String(seat.seat_number).padStart(2, '0')}</p><p className="mt-0.5 text-xs opacity-80">{seat.status.replaceAll('_', ' ')}</p></div><HealthLabel health={health} /></div>
      <p className="mt-3 truncate font-mono text-[11px] text-[#D2D2D2]" title={seat.namespace || undefined}>{seat.namespace || 'namespace pending'}</p>
      <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-3 border-y border-white/10 py-3 text-xs"><div><p className="opacity-70">AI requests</p><p className="mt-0.5 font-mono text-base font-bold text-white">{requests}</p></div><div><p className="opacity-70">P95 latency</p><p className="mt-0.5 font-mono text-base font-bold text-white">{p95 ? `${Math.round(p95 / 1000)}s` : '—'}</p></div><div><p className="opacity-70">Errors</p><p className="mt-0.5 font-mono text-base font-bold text-white">{errors}</p></div><div><p className="opacity-70">Tokens</p><p className="mt-0.5 font-mono text-base font-bold text-white">{tokens.toLocaleString()}</p></div></div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]"><div><span className="opacity-65">CPU</span><p className="font-mono text-white">{seat.resource_usage?.available ? `${seat.resource_usage.cpu_millicores ?? 0}m` : '—'}</p></div><div><span className="opacity-65">Memory</span><p className="font-mono text-white">{seat.resource_usage?.available ? `${seat.resource_usage.memory_mib ?? 0} MiB` : '—'}</p></div><div><span className="opacity-65">Pods ready</span><p className="font-mono text-white">{seat.resource_usage?.available ? `${seat.resource_usage.ready_pods ?? 0}/${seat.resource_usage.pod_count ?? 0}` : '—'}</p></div><div><span className="opacity-65">Restarts</span><p className="font-mono text-white">{seat.resource_usage?.available ? seat.resource_usage.restarts ?? 0 : '—'}</p></div></div>
      <div className="mt-auto flex items-end justify-between gap-2 pt-3 text-[11px]"><span className="opacity-75">Provisioned {formatOperationalDuration(seat.provisioning_seconds)}</span>{seat.detail_url && <Link to={seat.detail_url} className="font-semibold text-white underline decoration-white/40 hover:decoration-white">Inspect</Link>}</div>
    </article>;
  })}</div>;
}

function LabsView({ data, selectedLab, setSelectedLab }: { data: AdminObservability; selectedLab: string; setSelectedLab: (value: string) => void }) {
  const activeLabs = data.provisioning.filter((lab) => !['completed', 'completed_with_errors', 'failed', 'reclaimed'].includes(lab.status));
  const labs = activeLabs.length ? activeLabs : data.provisioning;
  const lab = labs.find((item) => item.order_id === selectedLab) || labs[0];
  if (!lab) return <EmptyState>No lab observations are available.</EmptyState>;
  const grafana = grafanaDrilldownUrl(data.grafana.url, lab);
  return <div className="space-y-5">
    <div className="flex flex-col justify-between gap-4 rounded-lg border border-[#303030] bg-[#202020] p-5 lg:flex-row lg:items-end"><div className="min-w-0 flex-1"><label htmlFor="lab-observability-select" className="mb-2 block text-xs font-bold uppercase tracking-wider text-[#8A8D90]">Select a lab</label><select id="lab-observability-select" value={lab.order_id} onChange={(event) => setSelectedLab(event.target.value)} className="w-full max-w-2xl rounded border border-[#555] bg-[#151515] px-3 py-2.5 text-sm text-white">{labs.map((option) => <option key={option.order_id} value={option.order_id}>{option.name} · {option.ready_seats}/{option.seats_requested} seats · {option.cluster_ref || 'unassigned'}</option>)}</select><p className="mt-2 truncate font-mono text-xs text-[#6A6E73]">{lab.catalog_item_id} · {lab.order_id}</p></div><div className="flex flex-wrap items-center gap-4 text-sm"><span><strong className="text-white">{lab.ready_seats}/{lab.seats_requested}</strong> <span className="text-[#8A8D90]">ready</span></span><span><strong className={lab.failed_seats ? 'text-[#FA6868]' : 'text-white'}>{lab.failed_seats}</strong> <span className="text-[#8A8D90]">failed</span></span>{lab.detail_url && <Link to={lab.detail_url} className="text-[#73BCF7] hover:underline">Manage lab</Link>}{grafana && <a href={grafana} target="_blank" rel="noreferrer" className="text-[#B6A6E9] hover:underline">Telemetry ↗</a>}</div></div>
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2 className="text-lg font-semibold text-white">Seat health</h2><p className="text-sm text-[#8A8D90]">Lifecycle and attributed AI usage for every participant environment.</p></div><Legend /></div><SeatGrid data={data} lab={lab} />
  </div>;
}

function ModelsView({ data }: { data: AdminObservability }) {
  return <div className="space-y-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2 className="text-lg font-semibold text-white">AI model pressure</h2><p className="text-sm text-[#8A8D90]">Serving readiness, replica pressure, latency, usage, and failures.</p></div><Legend /></div>{data.llm.telemetry_gaps.length > 0 && <div className="rounded border border-[#F0AB00]/50 bg-[#3a2d0b] p-4 text-sm text-[#F4C145]"><strong>Telemetry gaps:</strong> {data.llm.telemetry_gaps.join(' · ')}</div>}{data.llm.models.length === 0 ? <EmptyState>No model endpoint inventory is available.</EmptyState> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.llm.models.map((model) => {
    const traffic = data.llm.attribution.filter((row) => row.model_id === model.model_id);
    const health = modelHealth(model, traffic);
    const requests = traffic.reduce((sum, row) => sum + row.requests, 0);
    const errors = traffic.reduce((sum, row) => sum + row.errors, 0);
    const limited = traffic.reduce((sum, row) => sum + row.rate_limited, 0);
    const tokens = traffic.reduce((sum, row) => sum + row.total_tokens, 0);
    const p95 = Math.max(0, ...traffic.map((row) => row.p95_latency_ms || 0));
    return <article key={model.model_id} className={`rounded-lg border p-5 ${TONE_CLASSES[health.tone]}`}><div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold text-white">{model.display_name}</h3><p className="font-mono text-xs opacity-75">{model.model_id}</p></div><HealthLabel health={health} /></div><div className="my-4 rounded bg-black/15 p-4 text-center"><p className="text-xs uppercase tracking-wider opacity-70">Ready replicas</p><p className="mt-1 text-3xl font-bold text-white">{model.ready_replicas} / {model.desired_replicas}</p></div><div className="grid grid-cols-4 gap-2 text-center text-xs"><div><p className="opacity-70">Requests</p><p className="font-mono text-white">{requests}</p></div><div><p className="opacity-70">P95</p><p className="font-mono text-white">{p95 ? `${Math.round(p95 / 1000)}s` : '—'}</p></div><div><p className="opacity-70">Errors</p><p className="font-mono text-white">{errors}</p></div><div><p className="opacity-70">Limited</p><p className="font-mono text-white">{limited}</p></div></div><div className="mt-4 space-y-1 border-t border-white/10 pt-3 text-xs"><p><span className="opacity-65">Hardware:</span> {model.hardware || 'unknown'}</p><p><span className="opacity-65">Backend:</span> {model.backend || 'unknown'}</p><p><span className="opacity-65">Route:</span> {model.route}</p><p><span className="opacity-65">Tokens:</span> {tokens.toLocaleString()}</p></div></article>;
  })}</div>}</div>;
}

function ClustersView({ data }: { data: AdminObservability }) {
  return <div className="space-y-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2 className="text-lg font-semibold text-white">Cluster performance</h2><p className="text-sm text-[#8A8D90]">Placement eligibility and remaining compute, memory, and pod headroom.</p></div><Legend /></div>{data.clusters.length === 0 ? <EmptyState>No cluster observations are available.</EmptyState> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.clusters.map((cluster) => { const health = clusterHealth(cluster); return <article key={cluster.cluster_id} className={`rounded-lg border p-5 ${TONE_CLASSES[health.tone]}`}><div className="flex items-start justify-between gap-3"><div><h3 className="text-lg font-semibold text-white">{cluster.cluster_name || cluster.cluster_id}</h3><p className="font-mono text-xs opacity-75">{cluster.cluster_id}</p></div><HealthLabel health={health} /></div><div className="my-5 grid grid-cols-3 gap-2 text-center"><div className="rounded bg-black/15 p-3"><p className="text-xs opacity-70">CPU free</p><p className="mt-1 font-mono text-lg font-bold text-white">{Math.round(cluster.available_cpu_millicores / 1000)} cores</p></div><div className="rounded bg-black/15 p-3"><p className="text-xs opacity-70">Memory</p><p className="mt-1 font-mono text-lg font-bold text-white">{Math.round(cluster.available_memory_mib / 1024)} GiB</p></div><div className="rounded bg-black/15 p-3"><p className="text-xs opacity-70">Pod slots</p><p className="mt-1 font-mono text-lg font-bold text-white">{cluster.available_pods}</p></div></div><div className="grid grid-cols-3 gap-2 border-t border-white/10 pt-3 text-center text-xs"><div><p className="opacity-70">Workshops</p><p className="font-mono text-white">{cluster.active_workshops}</p></div><div><p className="opacity-70">Seats</p><p className="font-mono text-white">{cluster.active_seats}</p></div><div><p className="opacity-70">Sessions</p><p className="font-mono text-white">{cluster.active_sessions}</p></div></div><p className="mt-4 text-xs opacity-80">{health.reasons.join(' · ')}</p></article>; })}</div>}</div>;
}

function EventsView({ data, lifecycle }: { data: AdminObservability; lifecycle: LifecycleHealth | null }) {
  return <div className="space-y-5"><div><h2 className="text-lg font-semibold text-white">Lifecycle and platform events</h2><p className="text-sm text-[#8A8D90]">A single queue for failed seats, in-flight work, cleanup, worker retries, and telemetry gaps.</p></div><div className="grid gap-5 xl:grid-cols-3">
    <section className="rounded-lg border border-[#303030] bg-[#202020] p-4"><h3 className="font-semibold text-white">Attention queue</h3><p className="mb-3 text-xs text-[#8A8D90]">Failures, cleanup, and remediation state</p><div className="space-y-2">{data.resolution.length === 0 ? <p className="rounded bg-[#181818] p-4 text-sm text-[#8A8D90]">No seat alerts.</p> : data.resolution.map((row) => <div key={`${row.order_id}-${row.seat_number}-${row.status}`} className={`rounded border p-3 text-xs ${row.state === 'attention' ? TONE_CLASSES.danger : TONE_CLASSES.warning}`}><div className="flex justify-between gap-2"><strong className="text-white">{row.name} · seat {row.seat_number}</strong><span>{row.status.replaceAll('_', ' ')}</span></div><p className="mt-1 opacity-80">{row.message || row.state}</p>{row.detail_url && <Link to={row.detail_url} className="mt-2 inline-block text-white underline">Inspect</Link>}</div>)}</div></section>
    <section className="rounded-lg border border-[#303030] bg-[#202020] p-4"><h3 className="font-semibold text-white">In-flight operations</h3><p className="mb-3 text-xs text-[#8A8D90]">Provisioning, validation, and reclamation</p><div className="space-y-2">{data.inflight.length === 0 ? <p className="rounded bg-[#181818] p-4 text-sm text-[#8A8D90]">No seat operations in flight.</p> : data.inflight.map((row) => <div key={row.order_id} className={`rounded border p-3 text-xs ${TONE_CLASSES.info}`}><div className="flex justify-between gap-2"><strong className="text-white">{row.name}</strong><span>{row.inflight_seats} seats</span></div><p className="mt-1 opacity-80">{Object.entries(row.stage_counts).map(([stage, count]) => `${stage}: ${count}`).join(' · ')}</p><p className="mt-1 opacity-70">Oldest {formatOperationalDuration(row.oldest_seconds)}</p></div>)}</div></section>
    <section className="rounded-lg border border-[#303030] bg-[#202020] p-4"><h3 className="font-semibold text-white">Lifecycle workers</h3><p className="mb-3 text-xs text-[#8A8D90]">Durable jobs, retries, leases, and takeovers</p><div className="space-y-2">{!lifecycle || lifecycle.jobs.length === 0 ? <p className="rounded bg-[#181818] p-4 text-sm text-[#8A8D90]">No active lifecycle jobs.</p> : lifecycle.jobs.map((job) => <div key={job.job_id} className={`rounded border p-3 text-xs ${job.status === 'failed' ? TONE_CLASSES.danger : job.status === 'running' ? TONE_CLASSES.info : TONE_CLASSES.muted}`}><div className="flex justify-between gap-2"><strong className="text-white">{job.operation.replaceAll('_', ' ')}</strong><span>{job.status}</span></div><p className="mt-1 font-mono opacity-70">{job.cluster_ref || 'unassigned'} · attempt {job.attempts}/{job.max_attempts}</p>{job.last_error && <p className="mt-1 text-[#FA6868]">{job.last_error}</p>}</div>)}</div>{data.llm.telemetry_gaps.length > 0 && <div className={`mt-3 rounded border p-3 text-xs ${TONE_CLASSES.warning}`}><strong>Telemetry gaps</strong><p className="mt-1">{data.llm.telemetry_gaps.join(' · ')}</p></div>}</section>
  </div></div>;
}

function EmptyState({ children }: { children: string }) { return <p className="rounded-lg border border-[#303030] bg-[#202020] p-10 text-center text-sm text-[#8A8D90]">{children}</p>; }

export default function Observability() {
  const [data, setData] = useState<AdminObservability | null>(null);
  const [lifecycle, setLifecycle] = useState<LifecycleHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>('labs');
  const [selectedLab, setSelectedLab] = useState('');
  const load = useCallback(() => {
    api.getAdminObservability().then((payload) => { setData(payload); setError(null); setSelectedLab((current) => payload.provisioning.some((lab) => lab.order_id === current) ? current : (payload.provisioning.find((lab) => !['completed', 'completed_with_errors', 'failed', 'reclaimed'].includes(lab.status))?.order_id || payload.provisioning[0]?.order_id || '')); }).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause))).finally(() => setLoading(false));
    api.getLifecycleHealth().then(setLifecycle).catch(() => setLifecycle(null));
  }, []);
  useEffect(() => { load(); const interval = window.setInterval(load, 15_000); return () => window.clearInterval(interval); }, [load]);
  const alertCount = useMemo(() => (data?.summary.seats_attention || 0) + (lifecycle?.summary.failed || 0), [data, lifecycle]);
  if (loading) return <div className="mx-auto max-w-7xl px-6 py-10 text-[#8A8D90]">Loading the operations view…</div>;
  if (!data) return <div className="mx-auto max-w-7xl px-6 py-10"><div className="rounded-lg border border-[#C9190B]/40 bg-[#C9190B]/10 p-6 text-[#FA6868]">Observability data is unavailable. {error}<button onClick={load} className="ml-3 text-[#73BCF7] underline">Retry</button></div></div>;
  return <div className="mx-auto max-w-[1600px] space-y-6 px-6 py-8 lg:px-8">
    <header className="flex flex-col justify-between gap-4 md:flex-row md:items-start"><div><p className="mb-1 text-xs font-bold uppercase tracking-[0.18em] text-[#73BCF7]">Pilot control room</p><h1 className="text-3xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Lab observability</h1><p className="mt-2 max-w-3xl text-sm text-[#8A8D90]">One operational view across participant seats, AI serving, and execution clusters. Refreshes every 15 seconds.</p></div><div className="flex items-center gap-3"><span className="text-xs text-[#6A6E73]">Updated {new Date(data.generated_at).toLocaleTimeString()}</span><button onClick={load} className="rounded border border-[#555] px-3 py-2 text-xs font-medium text-[#D2D2D2] hover:border-[#8A8D90]">Refresh</button>{data.grafana.configured && data.grafana.url && <a href={data.grafana.url} target="_blank" rel="noreferrer" className="rounded bg-[#0071C5] px-3 py-2 text-xs font-semibold text-white hover:bg-[#005A9C]">Grafana ↗</a>}</div></header>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-6"><Metric label="Clusters" value={`${data.summary.clusters_healthy}/${data.summary.clusters_total}`} detail="healthy" tone={data.summary.clusters_healthy === data.summary.clusters_total ? 'text-[#73BC63]' : 'text-[#F4C145]'} /><Metric label="Active labs" value={data.summary.labs_active} detail="orders" /><Metric label="Ready seats" value={data.summary.seats_active} detail="participant environments" tone="text-[#73BC63]" /><Metric label="In flight" value={data.summary.seats_inflight} detail="seat operations" tone="text-[#73BCF7]" /><Metric label="Alerts" value={alertCount} detail="seat + lifecycle" tone={alertCount ? 'text-[#FA6868]' : 'text-[#73BC63]'} /><Metric label="AI requests" value={data.llm.summary.requests_observed} detail={`${data.llm.summary.attributed_requests} attributed`} tone="text-[#B6A6E9]" /></div>
    <div className="grid grid-cols-2 gap-2 rounded-lg border border-[#303030] bg-[#191919] p-3 text-xs sm:grid-cols-5"><span className="text-[#8A8D90]">In flight <strong className="ml-1 text-white">{data.summary.seats_inflight}</strong></span><span className="text-[#8A8D90]">Needs attention <strong className={`ml-1 ${data.summary.seats_attention ? 'text-[#FA6868]' : 'text-white'}`}>{data.summary.seats_attention}</strong></span><span className="text-[#8A8D90]">Lifecycle queued/running <strong className="ml-1 text-white">{(lifecycle?.summary.queued || 0)}/{(lifecycle?.summary.running || 0)}</strong></span><span className="text-[#8A8D90]">Lifecycle failed <strong className={`ml-1 ${(lifecycle?.summary.failed || 0) ? 'text-[#FA6868]' : 'text-white'}`}>{lifecycle?.summary.failed ?? '—'}</strong></span><span className="text-[#8A8D90]">Worker takeovers <strong className="ml-1 text-white">{lifecycle?.summary.takeovers ?? '—'}</strong></span></div>
    <section className="overflow-hidden rounded-lg border border-[#303030] bg-[#171717]"><div role="tablist" aria-label="Observability views" className="flex overflow-x-auto border-b border-[#303030]"><TabButton active={view === 'labs'} onClick={() => setView('labs')}>Labs & seats</TabButton><TabButton active={view === 'models'} onClick={() => setView('models')}>AI models</TabButton><TabButton active={view === 'clusters'} onClick={() => setView('clusters')}>Clusters</TabButton><TabButton active={view === 'events'} onClick={() => setView('events')}>Events & alerts</TabButton></div><div role="tabpanel" className="p-5 lg:p-6">{view === 'labs' && <LabsView data={data} selectedLab={selectedLab} setSelectedLab={setSelectedLab} />}{view === 'models' && <ModelsView data={data} />}{view === 'clusters' && <ClustersView data={data} />}{view === 'events' && <EventsView data={data} lifecycle={lifecycle} />}</div></section>
  </div>;
}
