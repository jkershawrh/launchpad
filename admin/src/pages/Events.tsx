import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { EventRecord } from '../api/types';

function clusterSummary(event: EventRecord) {
  const seats = new Map<string, number>();
  for (const allocation of event.capacity_preview.allocations) {
    seats.set(allocation.cluster_id, (seats.get(allocation.cluster_id) || 0) + allocation.seats);
  }
  return [...seats.entries()].sort(([left], [right]) => left.localeCompare(right));
}

export default function Events() {
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.listEvents()
      .then((data) => active && setEvents(data))
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : 'Unable to load events'))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 lg:px-8">
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#58A6E7]">Event orchestration</p>
        <h1 className="text-3xl font-bold text-white">Events</h1>
        <p className="mt-2 max-w-3xl text-sm text-[#A3A3A3]">
          Approved event demand, certified capacity, and persisted cluster placement. This view is read-only and cannot launch, reserve, or reclaim workshops.
        </p>
      </div>

      {loading && <p role="status" className="rounded border border-[#333] bg-[#212121] p-6 text-[#A3A3A3]">Loading approved events…</p>}
      {error && <p role="alert" className="rounded border border-[#C9190B] bg-[#2B1717] p-4 text-[#FF8D85]">Unable to load events: {error}</p>}
      {!loading && !error && events.length === 0 && (
        <div className="rounded border border-dashed border-[#555] bg-[#212121] p-10 text-center">
          <h2 className="text-lg font-semibold text-white">No approved events yet</h2>
          <p className="mt-2 text-sm text-[#A3A3A3]">Approved event manifests will appear here after their capacity contract passes.</p>
        </div>
      )}

      {!loading && !error && events.length > 0 && (
        <div className="space-y-5">
          {events.map((event) => {
            const manifest = event.manifest;
            const capacity = event.capacity_preview;
            return (
              <article key={manifest.event_id} className="overflow-hidden rounded border border-[#333] bg-[#212121]">
                <div className="flex flex-col justify-between gap-4 border-b border-[#333] p-5 md:flex-row md:items-start">
                  <div>
                    <h2 className="text-xl font-semibold text-white">{manifest.name}</h2>
                    <p className="mt-1 font-mono text-xs text-[#A3A3A3]">{manifest.event_id}</p>
                  </div>
                  <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${capacity.eligible ? 'border-[#3E8635] bg-[#18341C] text-[#92D400]' : 'border-[#C9190B] bg-[#2B1717] text-[#FF8D85]'}`}>
                    {capacity.eligible ? 'Capacity eligible' : 'Capacity unavailable'}
                  </span>
                </div>

                <div className="grid gap-px bg-[#333] sm:grid-cols-2 lg:grid-cols-4">
                  <div className="bg-[#212121] p-5"><p className="text-xs uppercase tracking-wide text-[#A3A3A3]">Demand</p><p className="mt-2 text-lg font-semibold text-white">{capacity.seat_environments} seat environments</p><p className="text-xs text-[#A3A3A3]">{capacity.participant_count} participants</p></div>
                  <div className="bg-[#212121] p-5"><p className="text-xs uppercase tracking-wide text-[#A3A3A3]">Schedule</p><p className="mt-2 text-lg font-semibold text-white">{manifest.cohorts.length} cohorts</p><p className="text-xs text-[#A3A3A3]">Peak {capacity.peak_concurrent_participants} concurrent</p></div>
                  <div className="bg-[#212121] p-5"><p className="text-xs uppercase tracking-wide text-[#A3A3A3]">Catalog</p><p className="mt-2 text-lg font-semibold text-white">{manifest.labs.length} labs</p><p className="text-xs text-[#A3A3A3]">Immutable releases</p></div>
                  <div className="bg-[#212121] p-5"><p className="text-xs uppercase tracking-wide text-[#A3A3A3]">Retention</p><p className="mt-2 text-lg font-semibold text-white">{manifest.retention.hours} hours</p><p className="text-xs text-[#A3A3A3]">From {manifest.retention.starts_from.replaceAll('_', ' ')}</p></div>
                </div>

                <div className="grid gap-6 p-5 lg:grid-cols-3">
                  <section><h3 className="text-sm font-semibold text-white">Placement</h3><div className="mt-3 space-y-2">{clusterSummary(event).map(([cluster, seats]) => <p key={cluster} className="rounded border border-[#444] bg-[#181818] px-3 py-2 text-sm text-[#D2D2D2]"><strong className="text-white">{cluster}</strong> · {seats} seats</p>)}</div></section>
                  <section><h3 className="text-sm font-semibold text-white">Labs</h3><div className="mt-3 space-y-2">{manifest.labs.map((lab) => <div key={lab.lab_ref} className="rounded border border-[#444] bg-[#181818] px-3 py-2"><p className="text-sm font-semibold text-white">{lab.catalog_id}</p><p className="font-mono text-xs text-[#A3A3A3]">{lab.catalog_release}</p></div>)}</div></section>
                  <section><h3 className="text-sm font-semibold text-white">Governance</h3><dl className="mt-3 space-y-2 text-sm"><div><dt className="text-[#A3A3A3]">Exposure</dt><dd className="text-white">{manifest.exposure_policy.replaceAll('_', ' ')}</dd></div><div><dt className="text-[#A3A3A3]">Owner</dt><dd className="text-white">{manifest.owner}</dd></div><div><dt className="text-[#A3A3A3]">Capacity evidence</dt><dd className="font-mono text-xs text-white">{capacity.matrix_id}</dd></div><div><dt className="text-[#A3A3A3]">Approved</dt><dd className="text-white">{new Date(event.created_at).toLocaleString()}</dd></div></dl></section>
                </div>
                <p className="border-t border-[#333] px-5 py-3 text-xs text-[#A3A3A3]">{capacity.explanation}</p>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
