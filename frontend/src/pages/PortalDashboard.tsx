import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem, LabSession, ShowbackRecord } from '../api/types';
import StatusBadge from '../components/StatusBadge';

export default function PortalDashboard() {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [showback, setShowback] = useState<ShowbackRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [renderedAt] = useState(() => Date.now());

  useEffect(() => {
    Promise.all([api.listCatalog(), api.listSessions()])
      .then(async ([catalogItems, labSessions]) => {
        setCatalog(catalogItems);
        setSessions(labSessions);
        const active = labSessions.filter((session) => session.status !== 'reclaimed');
        const usage = await Promise.all(
          active.map((session) => api.getShowback(session.session_id).catch(() => null)),
        );
        setShowback(usage.filter((record): record is ShowbackRecord => record !== null));
      })
      .finally(() => setLoading(false));
  }, []);

  const active = sessions.filter((session) =>
    ['provisioning', 'validating', 'ready', 'active'].includes(session.status),
  );
  const expiring = active.filter((session) => {
    if (!session.expires_at) return false;
    return new Date(session.expires_at).getTime() - renderedAt < 2 * 60 * 60 * 1000;
  });
  const requests = showback.reduce((total, record) => total + record.model_requests, 0);

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-8">
      <section className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#EE0000]">Partner AI Launchpad</p>
          <h1 className="mt-2 text-3xl font-bold text-white">Build, launch, and manage your AI labs</h1>
          <p className="mt-2 max-w-2xl text-sm text-[#A3A3A3]">
            Start from a validated catalog experience, follow provisioning progress, and manage active environments from one place.
          </p>
        </div>
        <Link to="/request" className="rounded bg-[#EE0000] px-5 py-3 text-sm font-semibold text-white hover:bg-[#B80000]">
          Request environment
        </Link>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Account summary">
        {[
          ['Active labs', active.length, 'Running or starting'],
          ['Catalog options', catalog.length, 'Available experiences'],
          ['Expiring soon', expiring.length, 'Within two hours'],
          ['Model requests', requests, 'Current usage records'],
        ].map(([label, value, detail]) => (
          <div key={label} className="border-t-2 border-[#EE0000] bg-[#212121] p-5">
            <p className="text-xs font-bold uppercase tracking-wider text-[#A3A3A3]">{label}</p>
            <p className="mt-2 text-3xl font-bold text-white">{loading ? '—' : value}</p>
            <p className="mt-1 text-xs text-[#6A6E73]">{detail}</p>
          </div>
        ))}
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.45fr_1fr]">
        <section className="rounded border border-[#333] bg-[#212121]">
          <div className="flex items-center justify-between border-b border-[#333] px-5 py-4">
            <div>
              <h2 className="font-semibold text-white">Active labs</h2>
              <p className="text-xs text-[#6A6E73]">Status, access, and expiration</p>
            </div>
            <Link to="/sessions" className="text-xs font-semibold text-[#58A6E7] hover:underline">View all</Link>
          </div>
          <div className="divide-y divide-[#333]">
            {active.length === 0 ? (
              <div className="px-5 py-10 text-center">
                <p className="text-sm text-[#A3A3A3]">No active labs.</p>
                <Link to="/catalog" className="mt-2 inline-block text-sm text-[#58A6E7] hover:underline">Browse the catalog</Link>
              </div>
            ) : active.slice(0, 5).map((session) => (
              <Link key={session.session_id} to={`/sessions/${session.session_id}`} className="flex items-center gap-4 px-5 py-4 hover:bg-white/5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-white">{session.catalog_item_id}</p>
                  <p className="mt-1 truncate font-mono text-xs text-[#6A6E73]">{session.session_id}</p>
                </div>
                <StatusBadge status={session.status} />
                <span className="text-xs text-[#A3A3A3]">
                  {session.expires_at ? new Date(session.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'No expiry'}
                </span>
              </Link>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <div className="rounded border border-[#333] bg-[#212121] p-5">
            <h2 className="font-semibold text-white">Start with the catalog</h2>
            <p className="mt-2 text-sm leading-6 text-[#A3A3A3]">Choose quick starts, guided builds, or configurable sandboxes matched to available capacity.</p>
            <Link to="/catalog" className="mt-4 inline-block text-sm font-semibold text-[#58A6E7] hover:underline">Explore experiences</Link>
          </div>
          <div className="rounded border border-[#333] bg-[#212121] p-5">
            <h2 className="font-semibold text-white">Usage and handoff</h2>
            <p className="mt-2 text-sm leading-6 text-[#A3A3A3]">Each lab records validation evidence, access instructions, repeatability, and showback.</p>
            <Link to="/sessions" className="mt-4 inline-block text-sm font-semibold text-[#58A6E7] hover:underline">Review lab records</Link>
          </div>
        </section>
      </div>
    </div>
  );
}
