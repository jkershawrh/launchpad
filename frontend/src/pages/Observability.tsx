import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type {
  AdminObservability,
  LifecycleHealth,
  ProvisioningObservation,
} from '../api/types';
import {
  filterProvisioning,
  formatOperationalDuration,
  grafanaDrilldownUrl,
  statusTone,
  type OperationalTone,
} from '../observabilityContract';

const TONE_CLASSES: Record<OperationalTone, string> = {
  success: 'border-[#3E8635]/40 bg-[#3E8635]/15 text-[#73BC63]',
  info: 'border-[#0071C5]/40 bg-[#0071C5]/15 text-[#73BCF7]',
  warning: 'border-[#F0AB00]/40 bg-[#F0AB00]/15 text-[#F4C145]',
  danger: 'border-[#C9190B]/40 bg-[#C9190B]/15 text-[#FA6868]',
  muted: 'border-[#555]/50 bg-white/5 text-[#B8BBBE]',
};

function Pill({ value }: { value: string }) {
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${TONE_CLASSES[statusTone(value)]}`}>
      {value.replaceAll('_', ' ')}
    </span>
  );
}

function Metric({ label, value, detail, tone = 'text-white' }: {
  label: string;
  value: string | number;
  detail: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-[#2e2e2e] bg-[#212121] p-4">
      <p className="text-xs font-bold uppercase tracking-wider text-[#8A8D90]">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${tone}`}>{value}</p>
      <p className="mt-1 text-xs text-[#8A8D90]">{detail}</p>
    </div>
  );
}

function SectionHeader({ number, title, detail }: { number: string; title: string; detail: string }) {
  return (
    <div className="mb-4 flex items-start gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#0071C5]/20 text-xs font-bold text-[#73BCF7]">{number}</span>
      <div>
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <p className="text-sm text-[#8A8D90]">{detail}</p>
      </div>
    </div>
  );
}

function SeatRows({ lab }: { lab: ProvisioningObservation }) {
  return (
    <div className="overflow-x-auto border-t border-[#333] bg-[#181818] px-4 py-3">
      <table className="w-full min-w-[760px] text-xs">
        <thead className="text-left uppercase tracking-wider text-[#8A8D90]">
          <tr>
            <th className="pb-2 pr-4">Seat</th>
            <th className="pb-2 pr-4">Status</th>
            <th className="pb-2 pr-4">Provisioning</th>
            <th className="pb-2 pr-4">Namespace</th>
            <th className="pb-2 pr-4">Resolution</th>
            <th className="pb-2">Details</th>
          </tr>
        </thead>
        <tbody>
          {lab.seats.map((seat) => (
            <tr key={`${lab.order_id}-${seat.seat_number}`} className="border-t border-[#2e2e2e] text-[#D2D2D2]">
              <td className="py-2 pr-4 font-mono">{seat.seat_number}</td>
              <td className="py-2 pr-4"><Pill value={seat.status} /></td>
              <td className="py-2 pr-4 font-mono">{formatOperationalDuration(seat.provisioning_seconds)}</td>
              <td className="max-w-[260px] truncate py-2 pr-4 font-mono text-[#8A8D90]">{seat.namespace || 'not created'}</td>
              <td className="py-2 pr-4">
                {seat.resolution_state === 'none' ? <span className="text-[#6A6E73]">—</span> : <Pill value={seat.resolution_state} />}
                {seat.error && <p className="mt-1 max-w-[320px] truncate text-[#FA6868]">{seat.error}</p>}
              </td>
              <td className="py-2">
                {seat.detail_url ? <Link className="text-[#73BCF7] hover:underline" to={seat.detail_url}>Open seat</Link> : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Observability() {
  const [data, setData] = useState<AdminObservability | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lifecycle, setLifecycle] = useState<LifecycleHealth | null>(null);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const load = useCallback(() => {
    api.getAdminObservability()
      .then((payload) => {
        setData(payload);
        setError(null);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)))
      .finally(() => setLoading(false));
    api.getLifecycleHealth()
      .then((payload) => {
        setLifecycle(payload);
        setLifecycleError(null);
      })
      .catch((cause) => {
        setLifecycle(null);
        setLifecycleError(cause instanceof Error ? cause.message : String(cause));
      });
  }, []);

  useEffect(() => {
    load();
    const interval = window.setInterval(load, 15_000);
    return () => window.clearInterval(interval);
  }, [load]);

  const labs = useMemo(
    () => filterProvisioning(data?.provisioning || [], query),
    [data?.provisioning, query],
  );

  const toggle = (orderId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(orderId)) next.delete(orderId);
      else next.add(orderId);
      return next;
    });
  };

  if (loading) {
    return <div className="mx-auto max-w-7xl px-6 py-10 text-[#8A8D90]">Loading the operations view…</div>;
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="rounded-lg border border-[#C9190B]/40 bg-[#C9190B]/10 p-6 text-[#FA6868]">
          Observability data is unavailable. {error}
          <button onClick={load} className="ml-3 text-[#73BCF7] underline">Retry</button>
        </div>
      </div>
    );
  }

  const summary = data.summary;
  const llm = data.llm;
  return (
    <div className="mx-auto max-w-7xl space-y-8 px-6 py-8 lg:px-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-[0.18em] text-[#73BCF7]">Pilot control room</p>
          <h1 className="text-3xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Lab observability</h1>
          <p className="mt-2 max-w-3xl text-sm text-[#8A8D90]">
            Follow each cluster, lab, and seat from provisioning through cleanup. This workflow view refreshes every 15 seconds.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[#6A6E73]">Updated {new Date(data.generated_at).toLocaleTimeString()}</span>
          <button onClick={load} className="rounded border border-[#555] px-3 py-2 text-xs font-medium text-[#D2D2D2] hover:border-[#8A8D90]">Refresh</button>
          {data.grafana.configured && data.grafana.url && (
            <a href={data.grafana.url} target="_blank" rel="noreferrer" className="rounded bg-[#0071C5] px-3 py-2 text-xs font-semibold text-white hover:bg-[#005A9C]">
              Open Grafana telemetry ↗
            </a>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Metric label="Cluster health" value={`${summary.clusters_healthy}/${summary.clusters_total}`} detail="healthy targets" tone={summary.clusters_healthy === summary.clusters_total ? 'text-[#73BC63]' : 'text-[#F4C145]'} />
        <Metric label="Active labs" value={summary.labs_active} detail="orders in lifecycle" />
        <Metric label="Available seats" value={summary.seats_active} detail="ready or active" tone="text-[#73BC63]" />
        <Metric label="In flight" value={summary.seats_inflight} detail="seat operations" tone="text-[#73BCF7]" />
        <Metric label="Needs attention" value={summary.seats_attention} detail="seat failures" tone={summary.seats_attention ? 'text-[#FA6868]' : 'text-[#73BC63]'} />
        <Metric label="LLM requests" value={llm.summary.requests_observed} detail={`${llm.summary.attributed_requests} seat-attributed`} tone="text-[#B6A6E9]" />
      </div>

      <section className="rounded-lg border border-[#2e2e2e] bg-[#212121] p-5">
        <SectionHeader number="1" title="Cluster readiness and capacity" detail="Placement eligibility and remaining CPU, memory, and pod slots." />
        {data.clusters.length === 0 ? (
          <p className="rounded bg-[#181818] p-5 text-center text-sm text-[#8A8D90]">No execution-cluster observations are available.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.clusters.map((cluster) => (
              <div key={cluster.cluster_id} className="rounded border border-[#333] bg-[#181818] p-4">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-white">{cluster.cluster_name || cluster.cluster_id}</p>
                    <p className="font-mono text-xs text-[#6A6E73]">{cluster.cluster_id}</p>
                  </div>
                  <Pill value={cluster.eligible ? 'eligible' : cluster.healthy ? 'degraded' : 'unreachable'} />
                </div>
                <div className="grid grid-cols-3 gap-3 border-y border-[#2e2e2e] py-3 text-xs">
                  <div><p className="text-[#6A6E73]">CPU free</p><p className="mt-1 font-mono text-white">{Math.round(cluster.available_cpu_millicores / 1000)} cores</p></div>
                  <div><p className="text-[#6A6E73]">Memory free</p><p className="mt-1 font-mono text-white">{Math.round(cluster.available_memory_mib / 1024)} GiB</p></div>
                  <div><p className="text-[#6A6E73]">Pod slots</p><p className="mt-1 font-mono text-white">{cluster.available_pods}</p></div>
                </div>
                <p className="mt-3 text-xs text-[#8A8D90]">{cluster.active_workshops} workshops · {cluster.active_seats} seats · {cluster.active_sessions} sessions</p>
                {cluster.reason && <p className="mt-2 text-xs text-[#6A6E73]">{cluster.reason}</p>}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-lg border border-[#2e2e2e] bg-[#212121]">
        <div className="p-5">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <SectionHeader number="2" title="Provisioning by lab and seat" detail="Collective readiness plus per-seat duration, status, namespace, and drill-down." />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter lab, cluster, or order…" className="w-full rounded border border-[#444] bg-[#181818] px-3 py-2 text-sm text-white placeholder:text-[#6A6E73] sm:w-72" />
          </div>
        </div>
        {labs.length === 0 ? (
          <p className="border-t border-[#333] p-8 text-center text-sm text-[#8A8D90]">No labs match this filter.</p>
        ) : labs.map((lab) => {
          const progress = lab.seats_requested ? Math.round((lab.ready_seats / lab.seats_requested) * 100) : 0;
          const grafana = grafanaDrilldownUrl(data.grafana.url, lab);
          return (
            <div key={lab.order_id} className="border-t border-[#333]">
              <div className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(220px,2fr)_110px_170px_135px_180px] lg:items-center">
                <div className="min-w-0">
                  <div className="flex items-center gap-2"><Pill value={lab.status} /><span className="text-xs text-[#6A6E73]">{lab.order_type}</span></div>
                  <p className="mt-2 truncate font-medium text-white">{lab.name}</p>
                  <p className="truncate font-mono text-xs text-[#6A6E73]">{lab.catalog_item_id} · {lab.cluster_ref || 'unassigned'}</p>
                </div>
                <div><p className="text-xs text-[#6A6E73]">Seats ready</p><p className="font-mono text-white">{lab.ready_seats}/{lab.seats_requested}</p></div>
                <div>
                  <div className="mb-1 flex justify-between text-xs text-[#8A8D90]"><span>Collective</span><span>{progress}%</span></div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[#333]"><div className="h-full rounded-full bg-[#3E8635]" style={{ width: `${progress}%` }} /></div>
                </div>
                <div><p className="text-xs text-[#6A6E73]">Slowest ready</p><p className="font-mono text-white">{formatOperationalDuration(lab.max_ready_seconds)}</p></div>
                <div className="flex flex-wrap justify-end gap-3 text-xs">
                  {lab.detail_url && <Link to={lab.detail_url} className="text-[#73BCF7] hover:underline">Manage</Link>}
                  {grafana && <a href={grafana} target="_blank" rel="noreferrer" className="text-[#B6A6E9] hover:underline">Telemetry ↗</a>}
                  <button onClick={() => toggle(lab.order_id)} className="text-[#D2D2D2] hover:text-white">{expanded.has(lab.order_id) ? 'Hide seats' : 'Show seats'}</button>
                </div>
              </div>
              {expanded.has(lab.order_id) && <SeatRows lab={lab} />}
            </div>
          );
        })}
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-lg border border-[#2e2e2e] bg-[#212121] p-5">
          <SectionHeader number="3" title="In-flight work" detail="Orders with seats still queued, provisioning, validating, resetting, or reclaiming." />
          {data.inflight.length === 0 ? <p className="rounded bg-[#181818] p-6 text-center text-sm text-[#8A8D90]">No seat operations are in flight.</p> : (
            <div className="space-y-2">
              {data.inflight.map((row) => (
                <div key={row.order_id} className="rounded border border-[#333] bg-[#181818] p-3">
                  <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-medium text-white">{row.name}</p><p className="font-mono text-xs text-[#6A6E73]">{row.cluster_ref || 'unassigned'}</p></div><span className="font-mono text-sm text-[#73BCF7]">{row.inflight_seats} seat{row.inflight_seats === 1 ? '' : 's'}</span></div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">{Object.entries(row.stage_counts).map(([stage, count]) => <span key={stage} className="text-xs text-[#8A8D90]"><Pill value={stage} /> <span className="ml-1">{count}</span></span>)}<span className="ml-auto text-xs text-[#6A6E73]">oldest {formatOperationalDuration(row.oldest_seconds)}</span></div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-lg border border-[#2e2e2e] bg-[#212121] p-5">
          <SectionHeader number="4" title="Resolution and cleanup" detail="Seat-level intervention queue and completed reclaim outcomes." />
          {data.resolution.length === 0 ? <p className="rounded bg-[#181818] p-6 text-center text-sm text-[#8A8D90]">No remediation or cleanup records require review.</p> : (
            <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
              {data.resolution.map((row) => (
                <div key={`${row.order_id}-${row.seat_number}-${row.status}`} className="rounded border border-[#333] bg-[#181818] p-3">
                  <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-medium text-white">{row.name} · seat {row.seat_number}</p><p className="font-mono text-xs text-[#6A6E73]">{row.cluster_ref || 'unassigned'} · {row.session_id || 'no session'}</p></div><Pill value={row.state} /></div>
                  <div className="mt-2 flex items-end justify-between gap-3"><p className={`text-xs ${row.message ? 'text-[#FA6868]' : 'text-[#8A8D90]'}`}>{row.message || row.status.replaceAll('_', ' ')}</p>{row.detail_url && <Link to={row.detail_url} className="shrink-0 text-xs text-[#73BCF7] hover:underline">Inspect</Link>}</div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="rounded-lg border border-[#2e2e2e] bg-[#212121] p-5">
        <SectionHeader number="5" title="AI and LLM traffic" detail="Endpoint readiness plus request, latency, error, rate-limit, token, route, backend, and seat attribution when telemetry supplies it." />
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-6">
          <Metric label="Models healthy" value={`${llm.summary.models_healthy}/${llm.summary.models_configured}`} detail={`${llm.summary.models_running} running`} tone={llm.summary.models_healthy === llm.summary.models_configured ? 'text-[#73BC63]' : 'text-[#F4C145]'} />
          <Metric label="Requests" value={llm.summary.requests_observed} detail={`${llm.summary.attributed_requests} attributed`} />
          <Metric label="Avg latency" value={llm.summary.avg_latency_ms == null ? '—' : `${Math.round(llm.summary.avg_latency_ms)}ms`} detail="observed requests" />
          <Metric label="P95 latency" value={llm.summary.p95_latency_ms == null ? '—' : `${Math.round(llm.summary.p95_latency_ms)}ms`} detail="observed requests" />
          <Metric label="Errors / limits" value={`${llm.summary.errors}/${llm.summary.rate_limited}`} detail="errors / rate limited" tone={llm.summary.errors ? 'text-[#FA6868]' : 'text-[#73BC63]'} />
          <Metric label="Tokens" value={llm.summary.total_tokens.toLocaleString()} detail={`${llm.summary.token_measurement} input + output`} tone="text-[#B6A6E9]" />
        </div>
        {llm.telemetry_gaps.length > 0 && (
          <div className="mb-5 rounded border border-[#F0AB00]/30 bg-[#F0AB00]/10 p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-[#F4C145]">Telemetry gaps</p>
            <ul className="mt-2 space-y-1 text-sm text-[#D2D2D2]">{llm.telemetry_gaps.map((gap) => <li key={gap}>• {gap}</li>)}</ul>
          </div>
        )}
        <div className="grid gap-5 xl:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[#8A8D90]">Model endpoints</p>
            <div className="space-y-2">{llm.models.length === 0 ? <p className="rounded bg-[#181818] p-5 text-sm text-[#8A8D90]">No endpoint inventory available.</p> : llm.models.map((model) => (
              <div key={model.model_id} className="rounded border border-[#333] bg-[#181818] p-3 text-xs">
                <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-medium text-white">{model.display_name}</p><p className="font-mono text-[#6A6E73]">{model.model_id}</p></div><Pill value={model.status} /></div>
                <div className="mt-3 grid grid-cols-3 gap-3 text-[#8A8D90]"><div><span className="block text-[#6A6E73]">Route</span>{model.route}</div><div><span className="block text-[#6A6E73]">Backend</span>{model.backend || 'unknown'}</div><div><span className="block text-[#6A6E73]">Replicas</span>{model.ready_replicas}/{model.desired_replicas}</div></div>
              </div>
            ))}</div>
          </div>
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[#8A8D90]">Requests by lab and seat</p>
            <div className="max-h-[360px] space-y-2 overflow-y-auto pr-1">{llm.attribution.length === 0 ? <p className="rounded bg-[#181818] p-5 text-sm text-[#8A8D90]">No seat-attributed LLM requests available.</p> : llm.attribution.map((row) => (
              <div key={`${row.session_id}-${row.model_id}`} className="rounded border border-[#333] bg-[#181818] p-3 text-xs">
                <div className="flex justify-between gap-3"><div><p className="font-medium text-white">{row.catalog_item_id} · seat {row.seat_number}</p><p className="font-mono text-[#6A6E73]">{row.cluster_ref || 'unknown'} · {row.model_id}</p></div><p className="font-mono text-[#B6A6E9]">{row.requests} req</p></div>
                <p className="mt-2 text-[#8A8D90]">avg {row.avg_latency_ms == null ? '—' : `${Math.round(row.avg_latency_ms)}ms`} · p95 {row.p95_latency_ms == null ? '—' : `${Math.round(row.p95_latency_ms)}ms`} · {row.errors} errors · {row.rate_limited} limited</p>
                <p className="mt-1 text-[#8A8D90]">{row.input_tokens.toLocaleString()} in + {row.output_tokens.toLocaleString()} out = {row.total_tokens.toLocaleString()} tokens · {row.token_measurement}</p>
              </div>
            ))}</div>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-[#2e2e2e] bg-[#212121] p-5">
        <SectionHeader number="6" title="Lifecycle queue and worker ownership" detail="Durable provisioning and reclaim jobs, lease health, retries, and worker takeovers." />
        {lifecycleError && (
          <p className="rounded border border-[#C9190B]/40 bg-[#C9190B]/10 p-4 text-sm text-[#FA6868]">
            Lifecycle queue data is unavailable. {lifecycleError}
          </p>
        )}
        {lifecycle && (
          <>
            <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-6">
              <Metric label="HA mode" value={lifecycle.enabled ? 'Enabled' : 'Disabled'} detail="durable lifecycle workers" tone={lifecycle.enabled ? 'text-[#73BC63]' : 'text-[#F4C145]'} />
              <Metric label="Queued" value={lifecycle.summary.queued} detail={`${lifecycle.summary.running} running`} tone="text-[#73BCF7]" />
              <Metric label="Reclaim pending" value={lifecycle.summary.reclaim_pending} detail="cleanup has priority" tone={lifecycle.summary.reclaim_pending ? 'text-[#F4C145]' : 'text-[#73BC63]'} />
              <Metric label="Failed" value={lifecycle.summary.failed} detail="exhausted retries" tone={lifecycle.summary.failed ? 'text-[#FA6868]' : 'text-[#73BC63]'} />
              <Metric label="Oldest active" value={formatOperationalDuration(lifecycle.summary.oldest_pending_age_seconds)} detail="queued or running" />
              <Metric label="Lease safety" value={`${lifecycle.summary.takeovers} takeover${lifecycle.summary.takeovers === 1 ? '' : 's'}`} detail={`${lifecycle.summary.expired_leases} expired leases`} tone={lifecycle.summary.expired_leases ? 'text-[#FA6868]' : 'text-[#73BC63]'} />
            </div>
            {lifecycle.jobs.length === 0 ? (
              <p className="rounded bg-[#181818] p-5 text-center text-sm text-[#8A8D90]">No lifecycle jobs have been recorded.</p>
            ) : (
              <div className="overflow-x-auto rounded border border-[#333] bg-[#181818]">
                <table className="w-full min-w-[900px] text-xs">
                  <thead className="text-left uppercase tracking-wider text-[#8A8D90]"><tr><th className="p-3">Operation</th><th className="p-3">Target</th><th className="p-3">Cluster</th><th className="p-3">Status</th><th className="p-3">Step</th><th className="p-3">Attempt</th><th className="p-3">Age</th></tr></thead>
                  <tbody>{lifecycle.jobs.slice(0, 25).map((job) => (
                    <tr key={job.job_id} className="border-t border-[#2e2e2e] text-[#D2D2D2]">
                      <td className="p-3 font-medium">{job.operation.replaceAll('_', ' ')}</td>
                      <td className="max-w-[240px] truncate p-3 font-mono text-[#8A8D90]">{job.aggregate_type}/{job.aggregate_id}</td>
                      <td className="p-3 font-mono">{job.cluster_ref || 'system'}</td>
                      <td className="p-3"><Pill value={job.status} /></td>
                      <td className="p-3">{job.step || '—'}</td>
                      <td className="p-3 font-mono">{job.attempts}/{job.max_attempts}</td>
                      <td className="p-3 font-mono">{formatOperationalDuration(job.age_seconds)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>

      {!data.grafana.configured && (
        <div className="rounded border border-[#555] bg-white/5 p-4 text-sm text-[#8A8D90]">
          Set <code className="text-[#D2D2D2]">GRAFANA_LAUNCHPAD_DASHBOARD_URL</code> to add resource, network, and latency history without duplicating time-series telemetry in Launchpad.
        </div>
      )}
    </div>
  );
}
