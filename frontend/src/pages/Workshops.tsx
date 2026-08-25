import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Workshop } from '../api/types';
import { workshopReadiness } from '../workshopOrderContract';

export default function Workshops() {
  const [items, setItems] = useState<Workshop[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api.listWorkshops().then(setItems).catch((err) => setError(err instanceof Error ? err.message : 'Unable to load workshops'));
  }, []);

  return <div className="mx-auto max-w-6xl px-4 py-10 text-white">
    <div className="flex items-center justify-between gap-4"><div><h1 className="text-3xl font-bold">Workshops</h1><p className="mt-1 text-[#A3A3A3]">Each order is one workshop with isolated participant seats.</p></div><Link to="/request?type=workshop" className="rounded bg-[#EE0000] px-4 py-2 font-semibold text-white hover:bg-[#B80000]">Create workshop</Link></div>
    {error && <div className="mt-6 rounded border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}
    <div className="mt-8 grid gap-4">
      {items.map((workshop) => {
        const ready = workshop.seats.filter((seat) => seat.status === 'ready').length;
        const readiness = workshopReadiness(ready, workshop.num_users);
        return <Link key={workshop.workshop_id} to={`/workshops/${workshop.workshop_id}`} className="rounded-lg border border-[#333] bg-[#212121] p-5 transition hover:border-[#58A6E7] hover:bg-[#292929]">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-bold">{workshop.name || workshop.catalog_item_id}</h2><p className="mt-1 font-mono text-xs text-[#A3A3A3]">{workshop.workshop_id}</p></div><span className="rounded-full bg-[#333] px-3 py-1 text-xs font-semibold">{workshop.status.replaceAll('_', ' ')}</span></div>
          <div className="mt-4 h-2 overflow-hidden rounded bg-[#333]"><div className="h-full bg-[#58A6E7]" style={{width: `${readiness}%`}} /></div>
          <p className="mt-2 text-sm">{ready} of {workshop.num_users} seats ready · {readiness}%</p>
        </Link>;
      })}
      {!error && items.length === 0 && <div className="rounded-lg border border-dashed border-[#555] bg-[#212121] p-10 text-center text-[#A3A3A3]">No workshop orders yet.</div>}
    </div>
  </div>;
}
