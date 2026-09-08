import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem, Workshop } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import { workshopReadiness } from '../workshopOrderContract';
import {
  filterWorkshops,
  newestWorkshopsFirst,
  type WorkshopFilter,
} from '../workshopList';

const FILTERS: Array<{ value: WorkshopFilter; label: string }> = [
  { value: 'current', label: 'Current (excluding completed)' },
  { value: 'ready', label: 'Ready / active' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'attention', label: 'Needs attention' },
  { value: 'completed', label: 'Completed' },
  { value: 'all', label: 'All workshops' },
];

export default function Workshops() {
  const [items, setItems] = useState<Workshop[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [filter, setFilter] = useState<WorkshopFilter>('current');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.listWorkshops(), api.listCatalog()])
      .then(([workshops, catalogItems]) => {
        setItems(newestWorkshopsFirst(workshops));
        setCatalog(catalogItems);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Unable to load workshops'))
      .finally(() => setLoading(false));
  }, []);

  const visibleItems = useMemo(() => filterWorkshops(items, filter), [items, filter]);
  const catalogNames = useMemo(
    () => new Map(catalog.map((item) => [item.catalog_item_id, item.display_name])),
    [catalog],
  );

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 text-white lg:px-8">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Workshops</h1>
          <p className="mt-1 text-sm text-[#6A6E73]">Manage each multi-seat order as one workshop.</p>
        </div>
        <Link to="/request?type=workshop" className="rounded bg-[#EE0000] px-4 py-2 text-sm font-semibold text-white hover:bg-[#B80000]">
          Create workshop
        </Link>
      </div>

      {error && <div className="mt-6 rounded border border-[#C9190B] bg-[#C9190B]/10 p-3 text-sm text-red-200">{error}</div>}

      <div className="mt-6 flex flex-col gap-3 border-b border-[#333] pb-5 sm:flex-row sm:items-end sm:justify-between">
        <label className="block max-w-sm flex-1 text-xs font-bold uppercase tracking-wider text-[#A3A3A3]">
          Show
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as WorkshopFilter)}
            className="mt-2 block w-full rounded border border-[#6A6E73] bg-[#151515] px-3 py-2 text-sm font-normal normal-case tracking-normal text-white"
          >
            {FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <p className="text-sm text-[#A3A3A3]" aria-live="polite">
          {loading ? 'Loading workshops…' : `${visibleItems.length} workshop${visibleItems.length === 1 ? '' : 's'}`}
        </p>
      </div>

      <div className="mt-5 grid gap-4">
        {visibleItems.map((workshop) => {
          const ready = workshop.seats.filter((seat) => seat.status === 'ready').length;
          const readiness = workshopReadiness(ready, workshop.num_users);
          const title = catalogNames.get(workshop.catalog_item_id) || workshop.name || workshop.catalog_item_id;
          return (
            <Link
              key={workshop.workshop_id}
              to={`/workshops/${workshop.workshop_id}`}
              className="rounded border border-[#333] bg-[#212121] p-5 transition hover:border-[#58A6E7] hover:bg-[#292929]"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-semibold">{title}</h2>
                  <p className="mt-1 text-xs text-[#A3A3A3]">
                    {workshop.cluster_ref || workshop.target_cluster || 'Cluster pending'} · {workshop.num_users} seats
                  </p>
                </div>
                <StatusBadge status={workshop.status} />
              </div>
              <div className="mt-4 h-2 overflow-hidden rounded bg-[#333]">
                <div className="h-full bg-[#58A6E7]" style={{ width: `${readiness}%` }} />
              </div>
              <p className="mt-2 text-sm text-[#A3A3A3]">{ready} of {workshop.num_users} seats ready · {readiness}%</p>
            </Link>
          );
        })}
        {!loading && !error && visibleItems.length === 0 && (
          <div className="rounded border border-dashed border-[#555] bg-[#212121] p-10 text-center text-sm text-[#A3A3A3]">
            No workshops match this selection.
          </div>
        )}
      </div>
    </div>
  );
}
