import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogIntakeDraft } from '../api/types';
import IntakeStageBadge from '../components/IntakeStageBadge';

export default function CatalogIntakes() {
  const [items, setItems] = useState<CatalogIntakeDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.listCatalogIntakes()
      .then((data) => active && setItems(data))
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : 'Unable to load intake submissions'))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 lg:px-8">
      <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#58A6E7]">Catalog governance</p>
          <h1 className="text-3xl font-bold text-white">Catalog intake</h1>
          <p className="mt-2 max-w-2xl text-sm text-[#A3A3A3]">Review repo-first, non-orderable drafts before evidence, target certification, approval, and promotion.</p>
        </div>
        <Link to="/intakes/new" className="inline-flex min-h-10 items-center justify-center rounded bg-[#EE0000] px-4 py-2 text-sm font-semibold text-white hover:bg-[#CC0000] focus:outline-none focus:ring-2 focus:ring-[#58A6E7] focus:ring-offset-2 focus:ring-offset-[#151515]">
          New intake submission
        </Link>
      </div>

      {loading && <p role="status" className="rounded border border-[#333] bg-[#212121] p-6 text-[#A3A3A3]">Loading intake submissions…</p>}
      {error && <p role="alert" className="rounded border border-[#C9190B] bg-[#2B1717] p-4 text-[#FF8D85]">Unable to load intake submissions: {error}</p>}
      {!loading && !error && items.length === 0 && <div className="rounded border border-dashed border-[#555] bg-[#212121] p-10 text-center"><h2 className="text-lg font-semibold text-white">No intake submissions yet</h2><p className="mt-2 text-sm text-[#A3A3A3]">Submit a pinned Git revision to begin the evidence-gated intake path.</p></div>}
      {!loading && !error && items.length > 0 && (
        <div className="overflow-hidden rounded border border-[#333] bg-[#212121]">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[780px] text-left text-sm">
              <caption className="sr-only">Catalog intake submissions</caption>
              <thead className="border-b border-[#333] bg-[#1A1A1A] text-xs uppercase tracking-wide text-[#A3A3A3]"><tr><th className="px-5 py-3">Submission</th><th className="px-5 py-3">Stage / state</th><th className="px-5 py-3">Scale request</th><th className="px-5 py-3">Targets</th><th className="px-5 py-3">Blockers</th><th className="px-5 py-3"><span className="sr-only">Open</span></th></tr></thead>
              <tbody>
                {items.map((item) => <tr key={item.intake_id} className="border-b border-[#333] last:border-0 hover:bg-white/[0.03]"><td className="px-5 py-4"><p className="font-semibold text-white">{item.requested.display_name}</p><p className="mt-1 font-mono text-xs text-[#A3A3A3]">{item.requested.catalog_item_id}</p></td><td className="px-5 py-4"><IntakeStageBadge state={item.state} /><p className="mt-2 text-xs text-[#A3A3A3]">Intake draft</p></td><td className="px-5 py-4 text-white"><strong>{item.requested.expected_scale}</strong> requested<p className="mt-1 text-xs text-[#A3A3A3]">Current ceiling: {item.defaults.maximum_seats}</p></td><td className="px-5 py-4 text-[#D2D2D2]">{item.supported_targets.length ? item.supported_targets.join(', ') : 'Unverified'}</td><td className="px-5 py-4"><span className="font-semibold text-[#F8C95E]">{item.blockers.length}</span><span className="text-[#A3A3A3]"> open</span></td><td className="px-5 py-4 text-right"><Link className="font-semibold text-[#58A6E7] hover:underline" to={`/intakes/${encodeURIComponent(item.intake_id)}`}>Review<span className="sr-only"> {item.requested.display_name}</span></Link></td></tr>)}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
