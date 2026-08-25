import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Workshop } from '../api/types';
import { reclaimActionLabel, workshopProgressLabel, workshopReadiness } from '../workshopOrderContract';

const terminalStatuses = new Set(['ready', 'partially_ready', 'failed', 'completed', 'completed_with_errors']);

export default function WorkshopDetail() {
  const { workshopId = '' } = useParams();
  const [workshop, setWorkshop] = useState<Workshop | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.getWorkshop(workshopId).then(setWorkshop).catch((err) => setError(err instanceof Error ? err.message : 'Unable to load workshop')), [workshopId]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { if (!workshop || !terminalStatuses.has(workshop.status)) void load(); }, 5000);
    return () => window.clearInterval(timer);
  }, [load, workshop?.status]);

  const reclaim = async () => {
    if (!window.confirm('Reclaim every seat and remove all workshop environments?')) return;
    setBusy(true); setError('');
    try { setWorkshop(await api.reclaimWorkshop(workshopId)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Reclaim failed'); }
    finally { setBusy(false); }
  };

  const retryFailed = async () => {
    setBusy(true); setError('');
    try { setWorkshop(await api.retryFailedWorkshopSeats(workshopId)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Retry failed'); }
    finally { setBusy(false); }
  };

  const exportLinks = async () => {
    if (!workshop) return;
    const rows = ['seat,participant,status,showroom_url', ...workshop.seats.map((seat) => `${seat.seat_number},${seat.participant_id || ''},${seat.status},${seat.showroom_url || seat.lab_url || ''}`)];
    await navigator.clipboard.writeText(rows.join('\n'));
  };

  if (!workshop) return <div className="mx-auto max-w-6xl px-4 py-10">{error || 'Loading workshop…'}</div>;
  const ready = workshop.seats.filter((seat) => seat.status === 'ready').length;
  const reclaimed = workshop.seats.filter((seat) => seat.status === 'reclaimed').length;
  const reclaiming = workshop.status === 'reclaiming';
  const readiness = workshopReadiness(ready, workshop.num_users);
  const progressLabel = workshopProgressLabel(workshop.status, ready, reclaimed, workshop.num_users);
  const readinessFailures = Object.entries(
    (workshop.metadata.readiness_failures || {}) as Record<string, string>,
  );
  const failedReclaims = Array.isArray(workshop.metadata.failed_reclaims)
    ? workshop.metadata.failed_reclaims as Array<{session_id?: string; error?: string}>
    : [];
  return <div className="mx-auto max-w-6xl px-4 py-10 text-white">
    <Link to="/workshops" className="text-sm text-[#58A6E7]">← All workshops</Link>
    <div className="mt-4 flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-3xl font-bold">{workshop.name || workshop.catalog_item_id}</h1><p className="mt-1 font-mono text-xs text-[#6A6E73]">{workshop.workshop_id}</p><p className="mt-2 text-sm font-semibold">One workshop · {workshop.num_users} participant seats</p></div><div className="flex gap-2"><button onClick={exportLinks} className="rounded border border-[#6A6E73] px-4 py-2 text-sm font-semibold">Copy seat CSV</button>{workshop.seats.some((seat) => seat.status === 'failed') && !reclaiming && <button disabled={busy} onClick={retryFailed} className="rounded bg-[#0068B5] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Retry failed seats</button>}{!['completed', 'completed_with_errors'].includes(workshop.status) && <button disabled={busy || reclaiming} onClick={reclaim} className="rounded bg-[#EE0000] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{reclaiming ? `Reclaiming ${reclaimed}/${workshop.num_users}` : reclaimActionLabel(workshop.status)}</button>}</div></div>
    {error && <div className="mt-5 rounded border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}
    {readinessFailures.length > 0 && <section className="mt-5 rounded border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"><b>Workshop readiness needs attention</b><p className="mt-1">{readinessFailures.length} seat endpoint{readinessFailures.length === 1 ? '' : 's'} did not remain stable. Review the affected seats below, then retry them.</p></section>}
    {(workshop.status === 'completed_with_errors' || failedReclaims.length > 0) && <section className="mt-5 rounded border border-red-300 bg-red-50 p-4 text-sm text-red-800"><b>Cleanup completed with errors</b><p className="mt-1">{failedReclaims.length || 'Some'} seat cleanup operation{failedReclaims.length === 1 ? '' : 's'} require operator attention.</p></section>}
    <section className="mt-6 rounded-lg bg-[#151515] p-6 text-white"><div className="flex justify-between gap-4"><b>{workshop.status.replaceAll('_', ' ')}</b><span className="text-right">{progressLabel}</span></div><div className="mt-3 h-2 overflow-hidden rounded bg-[#6A6E73]"><div className="h-full bg-[#00A878]" style={{width: `${reclaiming ? workshopReadiness(reclaimed, workshop.num_users) : readiness}%`}} /></div></section>
    <div className="mt-6 overflow-x-auto rounded-lg border border-[#333] bg-[#212121]"><table className="w-full text-left text-sm"><thead className="bg-[#151515] text-[#B8BBBE]"><tr><th className="p-3">Seat</th><th className="p-3">Participant</th><th className="p-3">Status</th><th className="p-3">Access</th><th className="p-3">Error</th></tr></thead><tbody>{workshop.seats.map((seat) => <tr key={seat.seat_id} className="border-t border-[#333]"><td className="p-3 font-semibold">{seat.seat_number}</td><td className="p-3 font-mono text-xs text-[#B8BBBE]">{seat.participant_id}</td><td className="p-3">{seat.status}</td><td className="p-3">{(seat.showroom_url || seat.lab_url) ? <a className="font-semibold text-[#58A6E7]" href={seat.showroom_url || seat.lab_url} target="_blank" rel="noreferrer">Open Showroom</a> : '—'}</td><td className="max-w-xs p-3 text-xs text-red-300">{seat.error || '—'}</td></tr>)}</tbody></table></div>
  </div>;
}
