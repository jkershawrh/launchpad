import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Workshop } from '../api/types';
import { workshopReadiness } from '../workshopOrderContract';

const terminalStatuses = new Set(['ready', 'partially_ready', 'failed', 'completed']);

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
  const readiness = workshopReadiness(ready, workshop.num_users);
  return <div className="mx-auto max-w-6xl px-4 py-10">
    <Link to="/workshops" className="text-sm text-[#0068B5]">← All workshops</Link>
    <div className="mt-4 flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-3xl font-bold">{workshop.name || workshop.catalog_item_id}</h1><p className="mt-1 font-mono text-xs text-[#6A6E73]">{workshop.workshop_id}</p></div><div className="flex gap-2"><button onClick={exportLinks} className="rounded border border-[#6A6E73] px-4 py-2 text-sm font-semibold">Copy seat CSV</button>{workshop.seats.some((seat) => seat.status === 'failed') && <button disabled={busy} onClick={retryFailed} className="rounded bg-[#0068B5] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Retry failed seats</button>}{workshop.status !== 'completed' && <button disabled={busy} onClick={reclaim} className="rounded bg-[#EE0000] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Reclaim all</button>}</div></div>
    {error && <div className="mt-5 rounded border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}
    <section className="mt-6 rounded-lg bg-[#151515] p-6 text-white"><div className="flex justify-between"><b>{workshop.status.replaceAll('_', ' ')}</b><span>{ready}/{workshop.num_users} ready</span></div><div className="mt-3 h-2 overflow-hidden rounded bg-[#6A6E73]"><div className="h-full bg-[#00A878]" style={{width: `${readiness}%`}} /></div></section>
    <div className="mt-6 overflow-x-auto rounded-lg border border-[#D2D2D2] bg-white"><table className="w-full text-left text-sm"><thead className="bg-[#F0F0F0]"><tr><th className="p-3">Seat</th><th className="p-3">Participant</th><th className="p-3">Status</th><th className="p-3">Access</th><th className="p-3">Error</th></tr></thead><tbody>{workshop.seats.map((seat) => <tr key={seat.seat_id} className="border-t border-[#D2D2D2]"><td className="p-3 font-semibold">{seat.seat_number}</td><td className="p-3 font-mono text-xs">{seat.participant_id}</td><td className="p-3">{seat.status}</td><td className="p-3">{(seat.showroom_url || seat.lab_url) ? <a className="font-semibold text-[#0068B5]" href={seat.showroom_url || seat.lab_url} target="_blank" rel="noreferrer">Open Showroom</a> : '—'}</td><td className="max-w-xs p-3 text-xs text-red-700">{seat.error || '—'}</td></tr>)}</tbody></table></div>
  </div>;
}
