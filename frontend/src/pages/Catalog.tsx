import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';
import StatusBadge from '../components/StatusBadge';

const CATEGORY_LABELS: Record<string, string> = {
  quick_start: 'Quick Start',
  guided_build: 'Guided Build',
  open_sandbox: 'Open Sandbox',
};

const CATEGORY_BORDER: Record<string, string> = {
  quick_start: '#EE0000',
  guided_build: '#0071C5',
  open_sandbox: '#3E8635',
};

export default function Catalog() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = searchParams.get('category') || 'all';

  useEffect(() => {
    api.listCatalog().then((data) => { setItems(data); setLoading(false); });
  }, []);

  const filtered = filter === 'all' ? items : items.filter((i) => i.category === filter);

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Catalog</h1>
        <p className="text-[#6A6E73] text-sm mt-1">Browse available labs, guided builds, and sandboxes.</p>
      </div>

      <div className="flex gap-2">
        {['all', 'quick_start', 'guided_build', 'open_sandbox'].map((cat) => (
          <button
            key={cat}
            onClick={() => setSearchParams(cat === 'all' ? {} : { category: cat })}
            className={`px-3 py-1.5 rounded text-xs font-medium transition ${
              filter === cat
                ? 'bg-white/15 text-white'
                : 'text-[#6A6E73] hover:text-white hover:bg-white/10'
            }`}
          >
            {cat === 'all' ? 'All' : CATEGORY_LABELS[cat]}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-20 bg-[#212121] rounded-lg animate-pulse" />)}
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map((item) => (
            <div
              key={item.catalog_item_id}
              className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4 hover:border-[#555] transition"
              style={{ borderLeftWidth: '3px', borderLeftColor: CATEGORY_BORDER[item.category] || '#333' }}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-sm font-semibold text-white">{item.display_name}</h3>
                    <StatusBadge status={item.category} />
                    <span className="text-xs text-[#6A6E73]">v{item.version}</span>
                  </div>
                  <p className="text-[#6A6E73] text-xs mb-3">{item.description}</p>
                  <div className="flex flex-wrap gap-1">
                    {item.required_capabilities.map((cap) => (
                      <span key={cap} className="text-xs bg-[#1a1a1a] text-[#6A6E73] px-2 py-0.5 rounded">{cap}</span>
                    ))}
                  </div>
                </div>
                <Link
                  to={item.category === 'open_sandbox' ? '/sandbox' : `/demos?launch=${item.catalog_item_id}`}
                  className="ml-4 px-4 py-2 rounded text-xs font-medium text-white transition hover:opacity-90 shrink-0"
                  style={{ backgroundColor: 'var(--brand-primary)' }}
                >
                  {item.category === 'open_sandbox' ? 'Configure' : 'Launch'}
                </Link>
              </div>
              <div className="mt-2 flex gap-4 text-xs text-[#6A6E73]">
                {item.default_hardware_profile && <span>Hardware: {item.default_hardware_profile}</span>}
                {item.default_ttl && <span>TTL: {item.default_ttl}</span>}
                {item.default_quota_profile && <span>Quota: {item.default_quota_profile}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
