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

const CATEGORY_COLORS: Record<string, string> = {
  quick_start: 'border-l-[#EE0000]',
  guided_build: 'border-l-[#0068B5]',
  open_sandbox: 'border-l-[#3E8635]',
};

export default function Catalog() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = searchParams.get('category') || 'all';

  useEffect(() => {
    api.listCatalog().then((data) => {
      setItems(data);
      setLoading(false);
    });
  }, []);

  const filtered = filter === 'all' ? items : items.filter((i) => i.category === filter);

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">Catalog</h1>
      <p className="text-[#6A6E73] mb-8">Browse available labs, guided builds, and sandboxes.</p>

      <div className="flex gap-2 mb-8">
        {['all', 'quick_start', 'guided_build', 'open_sandbox'].map((cat) => (
          <button
            key={cat}
            onClick={() => setSearchParams(cat === 'all' ? {} : { category: cat })}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              filter === cat
                ? 'bg-[#151515] text-white'
                : 'bg-white text-[#6A6E73] border border-[#D2D2D2] hover:bg-gray-50'
            }`}
          >
            {cat === 'all' ? 'All' : CATEGORY_LABELS[cat]}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-[#6A6E73]">Loading catalog...</p>
      ) : (
        <div className="grid gap-4">
          {filtered.map((item) => (
            <div
              key={item.catalog_item_id}
              className={`bg-white rounded border border-[#D2D2D2] border-l-4 ${CATEGORY_COLORS[item.category]} p-6`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-[#151515]">{item.display_name}</h3>
                    <StatusBadge status={item.category} />
                    <span className="text-xs text-[#6A6E73]">v{item.version}</span>
                  </div>
                  <p className="text-[#6A6E73] text-sm mb-3">{item.description}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {item.required_capabilities.map((cap) => (
                      <span key={cap} className="text-xs bg-[#F0F0F0] text-[#151515] px-2 py-0.5 rounded">
                        {cap}
                      </span>
                    ))}
                    {item.optional_capabilities.map((cap) => (
                      <span key={cap} className="text-xs bg-white text-[#6A6E73] px-2 py-0.5 rounded border border-dashed border-[#D2D2D2]">
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
                <Link
                  to={item.category === 'open_sandbox' ? '/sandbox' : `/demos?launch=${item.catalog_item_id}`}
                  className="ml-4 px-4 py-2 bg-[#EE0000] text-white rounded text-sm font-medium hover:bg-[#A30000] transition-colors shrink-0"
                >
                  {item.category === 'open_sandbox' ? 'Configure' : 'Launch'}
                </Link>
              </div>
              <div className="mt-3 flex gap-4 text-xs text-[#6A6E73]">
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
