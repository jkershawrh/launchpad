import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem, LabSession } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import { currentLabSessions, historicalLabSessions, workshopSeatCount } from '../myLabsList';
import { newestSessionsFirst } from '../sessionSort';

function LabCard({ session, title }: { session: LabSession; title: string }) {
  return (
    <Link
      to={`/sessions/${session.session_id}`}
      className="flex flex-col gap-3 border-b border-[#333] px-5 py-4 last:border-0 hover:bg-white/5 sm:flex-row sm:items-center"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-white">{title}</p>
        <p className="mt-1 text-xs text-[#A3A3A3]">
          {session.cluster_ref || 'Cluster pending'} · {session.expires_at ? `Expires ${new Date(session.expires_at).toLocaleString()}` : 'No expiry set'}
        </p>
      </div>
      <StatusBadge status={session.status} />
      <span className="text-xs font-semibold text-[#58A6E7]">View lab</span>
    </Link>
  );
}

export default function Sessions() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.listSessions(), api.listCatalog()])
      .then(([items, catalogItems]) => {
        setSessions(newestSessionsFirst(items));
        setCatalog(catalogItems);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Unable to load labs'))
      .finally(() => setLoading(false));
  }, []);

  const current = useMemo(() => currentLabSessions(sessions), [sessions]);
  const history = useMemo(() => historicalLabSessions(sessions), [sessions]);
  const workshopSeats = useMemo(() => workshopSeatCount(sessions), [sessions]);
  const catalogNames = useMemo(
    () => new Map(catalog.map((item) => [item.catalog_item_id, item.display_name])),
    [catalog],
  );

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 lg:px-8">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">My labs</h1>
          <p className="mt-1 text-sm text-[#6A6E73]">Open current individual labs and review previous environments when needed.</p>
        </div>
        <Link to="/request" className="rounded bg-[#EE0000] px-4 py-2 text-sm font-semibold text-white hover:bg-[#B80000]">Request a lab</Link>
      </div>

      {error && <div className="mt-6 rounded border border-[#C9190B] bg-[#C9190B]/10 p-3 text-sm text-red-200">{error}</div>}

      {workshopSeats > 0 && (
        <div className="mt-6 flex flex-col gap-3 rounded border-l-4 border-[#58A6E7] bg-[#212121] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-[#A3A3A3]">
            {workshopSeats} workshop seat environment{workshopSeats === 1 ? ' is' : 's are'} managed with the workshop order.
          </p>
          <Link to="/workshops" className="shrink-0 text-sm font-semibold text-[#58A6E7] hover:underline">Manage workshops</Link>
        </div>
      )}

      <section className="mt-6 overflow-hidden rounded border border-[#333] bg-[#212121]" aria-labelledby="current-labs-heading">
        <div className="border-b border-[#333] px-5 py-4">
          <h2 id="current-labs-heading" className="font-semibold text-white">Current individual labs</h2>
          <p className="mt-1 text-xs text-[#6A6E73]">Active, starting, or requiring attention</p>
        </div>
        {loading ? (
          <p className="p-6 text-sm text-[#6A6E73]">Loading labs…</p>
        ) : current.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-sm text-[#A3A3A3]">No current individual labs.</p>
            <Link to="/catalog" className="mt-2 inline-block text-sm font-semibold text-[#58A6E7] hover:underline">Browse the catalog</Link>
          </div>
        ) : current.map((session) => (
          <LabCard
            key={session.session_id}
            session={session}
            title={catalogNames.get(session.catalog_item_id) || session.catalog_item_id}
          />
        ))}
      </section>

      {!loading && history.length > 0 && (
        <section className="mt-5">
          <button
            type="button"
            onClick={() => setShowHistory((visible) => !visible)}
            className="text-sm font-semibold text-[#58A6E7] hover:underline"
            aria-expanded={showHistory}
          >
            {showHistory ? 'Hide' : 'Show'} previous labs ({history.length})
          </button>
          {showHistory && (
            <div className="mt-3 overflow-hidden rounded border border-[#333] bg-[#212121]">
              {history.map((session) => (
                <LabCard
                  key={session.session_id}
                  session={session}
                  title={catalogNames.get(session.catalog_item_id) || session.catalog_item_id}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
