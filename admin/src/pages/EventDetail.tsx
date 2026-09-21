import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { EventAdmissionForecast, EventRecord, EventStatusResult } from '../api/types';

const stateTone: Record<EventStatusResult['state'], string> = {
  approved: 'border-[#58A6E7] bg-[#102d43] text-[#8CCCF5]',
  reserved: 'border-[#58A6E7] bg-[#102d43] text-[#8CCCF5]',
  progressing: 'border-[#F0AB00] bg-[#352A12] text-[#F8C95E]',
  awaiting_public_access: 'border-[#F0AB00] bg-[#352A12] text-[#F8C95E]',
  ready: 'border-[#3E8635] bg-[#18341C] text-[#92D400]',
  cleanup_evidence_pending: 'border-[#F0AB00] bg-[#352A12] text-[#F8C95E]',
  released: 'border-[#6A6E73] bg-[#292929] text-[#D2D2D2]',
  attention_required: 'border-[#C9190B] bg-[#2B1717] text-[#FF8D85]',
};

function label(value: string) { return value.replaceAll('_', ' '); }

export default function EventDetail() {
  const { eventId = '' } = useParams();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [status, setStatus] = useState<EventStatusResult | null>(null);
  const [forecast, setForecast] = useState<EventAdmissionForecast | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([api.getEvent(eventId), api.getEventStatus(eventId), api.getEventAdmissionForecast(eventId)])
      .then(([eventRecord, statusRecord, forecastRecord]) => { if (active) { setEvent(eventRecord); setStatus(statusRecord); setForecast(forecastRecord); } })
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : 'Unable to load event'));
    return () => { active = false; };
  }, [eventId]);

  if (error) return <div className="mx-auto max-w-7xl px-6 py-10 lg:px-8"><p role="alert" className="rounded border border-[#C9190B] bg-[#2B1717] p-4 text-[#FF8D85]">Unable to load event: {error}</p></div>;
  if (!event || !status || !forecast) return <div className="mx-auto max-w-7xl px-6 py-10 lg:px-8"><p role="status" className="rounded border border-[#333] bg-[#212121] p-6 text-[#A3A3A3]">Loading event status…</p></div>;

  const { manifest, capacity_preview: capacity } = event;
  return (
    <div className="mx-auto max-w-7xl px-6 py-10 lg:px-8">
      <Link to="/events" className="text-sm font-semibold text-[#58A6E7] hover:underline">← All events</Link>
      <div className="mt-5 flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div><p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#58A6E7]">Event operations · read only</p><h1 className="text-3xl font-bold text-white">{manifest.name}</h1><p className="mt-1 font-mono text-xs text-[#A3A3A3]">{manifest.event_id}</p></div>
        <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold capitalize ${stateTone[status.state]}`}>{label(status.state)}</span>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded border border-[#333] bg-[#212121] p-5"><p className="text-xs uppercase tracking-wide text-[#A3A3A3]">Seat readiness</p><p className="mt-2 text-2xl font-bold text-white">{status.summary.ready_seats} / {status.summary.seats} ready</p></div>
        <div className="rounded border border-[#333] bg-[#212121] p-5"><p className="text-xs uppercase tracking-wide text-[#A3A3A3]">Workshops</p><p className="mt-2 text-2xl font-bold text-white">{status.summary.workshops}</p><p className="text-xs text-[#A3A3A3]">{status.summary.public_workshops_active} public access active</p></div>
        <div className="rounded border border-[#333] bg-[#212121] p-5"><p className="text-xs uppercase tracking-wide text-[#A3A3A3]">Support</p><p className={`mt-2 text-lg font-semibold ${status.summary.failed_seats ? 'text-[#FF8D85]' : 'text-[#92D400]'}`}>{status.summary.failed_seats ? `${status.summary.failed_seats} failed seats` : 'No failed seats'}</p></div>
        <div className="rounded border border-[#333] bg-[#212121] p-5"><p className="text-xs uppercase tracking-wide text-[#A3A3A3]">Observed</p><p className="mt-2 text-sm font-semibold text-white">{new Date(status.observed_at).toLocaleString()}</p><p className="text-xs text-[#A3A3A3]">Reconciled status</p></div>
      </div>

      <section className="mt-8 overflow-hidden rounded border border-[#333] bg-[#212121]">
        <div className="border-b border-[#333] p-5"><h2 className="text-lg font-semibold text-white">Workshop readiness</h2><p className="mt-1 text-sm text-[#A3A3A3]">Each cohort and lab remains pinned to its reserved execution cluster.</p></div>
        <div className="overflow-x-auto"><table className="w-full min-w-[960px] text-left text-sm"><thead className="border-b border-[#333] bg-[#1A1A1A] text-xs uppercase tracking-wide text-[#A3A3A3]"><tr><th className="px-5 py-3">Cohort / lab</th><th className="px-5 py-3">Cluster</th><th className="px-5 py-3">Seats</th><th className="px-5 py-3">Lifecycle</th><th className="px-5 py-3">Access</th><th className="px-5 py-3"><span className="sr-only">Open</span></th></tr></thead><tbody>{status.workshops.map((workshop) => <tr key={workshop.reservation_id} className="border-b border-[#333] last:border-0"><td className="px-5 py-4"><p className="font-semibold text-white">{workshop.catalog_id}</p><p className="font-mono text-xs text-[#A3A3A3]">{workshop.cohort_id} · {workshop.catalog_release}</p></td><td className="px-5 py-4 font-semibold text-white">{workshop.cluster_ref}</td><td className="px-5 py-4 text-white">{workshop.ready_seats}/{workshop.seats} ready{workshop.failed_seats > 0 && <p className="text-xs text-[#FF8D85]">{workshop.failed_seats} failed</p>}</td><td className="px-5 py-4 text-[#D2D2D2]"><p>{label(workshop.workshop_status || workshop.reservation_status)}</p><p className="text-xs text-[#A3A3A3]">Job {label(workshop.lifecycle_job_status || 'not started')}</p></td><td className="px-5 py-4"><span className={workshop.public_access_state === 'active' ? 'text-[#92D400]' : 'text-[#F8C95E]'}>{workshop.public_access_state === 'active' ? 'Public access active' : label(workshop.public_access_state)}</span></td><td className="px-5 py-4 text-right">{workshop.public_url && <a href={workshop.public_url} className="font-semibold text-[#58A6E7] hover:underline" target="_blank" rel="noreferrer">Open {workshop.catalog_id}</a>}</td></tr>)}</tbody></table></div>
      </section>

      <section className="mt-8 rounded border border-[#333] bg-[#212121]">
        <div className="flex flex-col justify-between gap-3 border-b border-[#333] p-5 sm:flex-row sm:items-center"><div><h2 className="text-lg font-semibold text-white">Admission forecast</h2><p className="mt-1 text-sm text-[#A3A3A3]">Current certified headroom after existing reservations and this complete event. This is a read-only admission check, not a running-lab health verdict.</p></div><span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${forecast.eligible ? 'border-[#3E8635] bg-[#18341C] text-[#92D400]' : 'border-[#C9190B] bg-[#2B1717] text-[#FF8D85]'}`}>{forecast.eligible ? 'Admission protected' : 'Admission blocked'}</span></div>
        <div className="grid gap-4 p-5 lg:grid-cols-2">{forecast.clusters.map((cluster) => <article key={cluster.cluster_id} className="rounded border border-[#444] bg-[#181818] p-4"><div className="flex items-start justify-between gap-4"><div><h3 className="font-semibold text-white">{cluster.cluster_id}</h3><p className="mt-1 text-xs text-[#A3A3A3]">{cluster.catalog_releases.join(' · ')}</p></div><span className={cluster.eligible ? 'text-xs font-semibold text-[#92D400]' : 'text-xs font-semibold text-[#FF8D85]'}>{cluster.eligible ? 'Fits' : 'Blocked'}</span></div><div className="mt-4 grid grid-cols-3 gap-3 text-sm"><div><p className="text-xs text-[#A3A3A3]">Event demand</p><p className="font-semibold text-white">{cluster.demand.seats} seats</p></div><div><p className="text-xs text-[#A3A3A3]">Already reserved</p><p className="font-semibold text-white">{cluster.reserved.seats} seats</p></div><div><p className="text-xs text-[#A3A3A3]">After event</p><p className="font-semibold text-white">{cluster.remaining_after_event.seats} seats remaining</p></div></div><p className="mt-3 text-xs text-[#A3A3A3]">Demand: {cluster.demand.cpu_millicores / 1000} CPU cores · {cluster.demand.memory_mib} MiB · {cluster.demand.pods} pods · {cluster.demand.model_slots} model slots</p><p className="mt-4 text-xs text-[#A3A3A3]">Required: <span className="text-[#D2D2D2]">{cluster.required_capabilities.join(' · ') || 'none declared'}</span></p>{cluster.blockers.length > 0 && <p className="mt-2 text-xs text-[#FF8D85]">Blocked by: {cluster.blockers.join(', ')}</p>}</article>)}</div>
        <p className="border-t border-[#333] px-5 py-3 text-xs text-[#A3A3A3]">{forecast.explanation} Evidence {forecast.evidence_matches ? 'matches' : 'has drifted'}; {forecast.current_active_reservations} fleet reservations currently consume certified capacity. {capacity.dr_reserved_capacity} DR-reserved and {capacity.uncertified_capacity} uncertified seats are excluded. Artifact cold-pull, exact model health, and measured in-flight usage are separate gates.</p>
      </section>

      <div className="mt-8 grid gap-5 lg:grid-cols-2">
        <section className="rounded border border-[#333] bg-[#212121] p-5"><h2 className="text-lg font-semibold text-white">Capacity evidence</h2><dl className="mt-4 space-y-3 text-sm"><div><dt className="text-[#A3A3A3]">Matrix</dt><dd className="font-mono text-white">{capacity.matrix_id}</dd></div><div><dt className="text-[#A3A3A3]">Fleet snapshot</dt><dd className="break-all font-mono text-xs text-white">{capacity.fleet_snapshot_id}</dd></div><div><dt className="text-[#A3A3A3]">Reservation plan</dt><dd className="text-white">{status.reservation_complete ? 'Complete' : 'Incomplete'}</dd></div><div><dt className="text-[#A3A3A3]">Capacity decision</dt><dd className="text-white">{capacity.explanation}</dd></div></dl></section>
        <section className="rounded border border-[#333] bg-[#212121] p-5"><h2 className="text-lg font-semibold text-white">Event contract</h2><dl className="mt-4 grid grid-cols-2 gap-4 text-sm"><div><dt className="text-[#A3A3A3]">Cohorts</dt><dd className="text-white">{manifest.cohorts.length}</dd></div><div><dt className="text-[#A3A3A3]">Labs</dt><dd className="text-white">{manifest.labs.length}</dd></div><div><dt className="text-[#A3A3A3]">Exposure</dt><dd className="text-white">{label(manifest.exposure_policy)}</dd></div><div><dt className="text-[#A3A3A3]">Retention</dt><dd className="text-white">{manifest.retention.hours} hours</dd></div><div><dt className="text-[#A3A3A3]">Owner</dt><dd className="text-white">{manifest.owner}</dd></div><div><dt className="text-[#A3A3A3]">Approver</dt><dd className="text-white">{manifest.technical_approver}</dd></div></dl></section>
      </div>
    </div>
  );
}
