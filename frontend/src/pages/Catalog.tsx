import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import { catalogLaunchPath } from '../catalogNavigation';
import {
  LEARNING_LEVELS,
  LEARNING_STAGE,
  learningLevel,
  learningStage,
  prerequisites,
  recommendedNextItems,
  sortByLearningProgression,
} from '../catalogLearning';
import { participantCatalog } from '../catalogVisibility';

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
  const levelFilter = searchParams.get('level') || 'all';

  useEffect(() => {
    api.listCatalog().then((data) => {
      setItems(participantCatalog(data));
      setLoading(false);
    });
  }, []);

  const filtered = sortByLearningProgression(items.filter((item) => (
    (filter === 'all' || item.category === filter) &&
    (levelFilter === 'all' || learningLevel(item) === levelFilter)
  )));

  const updateFilter = (key: 'category' | 'level', value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === 'all') next.delete(key);
    else next.set(key, value);
    setSearchParams(next);
  };

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
            onClick={() => updateFilter('category', cat)}
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

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs font-medium uppercase tracking-wider text-[#6A6E73]">Learning level</span>
        {['all', ...LEARNING_LEVELS].map((level) => (
          <button
            key={level}
            onClick={() => updateFilter('level', level)}
            className={`rounded px-3 py-1.5 text-xs font-medium transition ${
              levelFilter === level
                ? 'bg-[#0068B5] text-white'
                : 'bg-[#212121] text-[#8A8D90] hover:bg-white/10 hover:text-white'
            }`}
          >
            {level === 'all' ? 'All levels' : `${level} · ${LEARNING_STAGE[level as keyof typeof LEARNING_STAGE]}`}
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
                    {learningLevel(item) && (
                      <span className="rounded bg-[#0068B5]/20 px-2 py-0.5 text-xs font-semibold text-[#73BCF7]">
                        {learningLevel(item)} · {learningStage(item)}
                      </span>
                    )}
                    <StatusBadge status={item.category} />
                    <span className="text-xs text-[#6A6E73]">v{item.version}</span>
                  </div>
                  <p className="text-[#6A6E73] text-xs mb-3">{item.description}</p>
                  <div className="flex flex-wrap gap-1">
                    {item.required_capabilities.map((cap) => (
                      <span key={cap} className="text-xs bg-[#1a1a1a] text-[#6A6E73] px-2 py-0.5 rounded">{cap}</span>
                    ))}
                  </div>
                  {prerequisites(item).length > 0 && (
                    <p className="mt-3 text-xs text-[#8A8D90]">
                      Prerequisite: {prerequisites(item).map((id) => items.find((entry) => entry.catalog_item_id === id)?.display_name || id).join(', ')}
                    </p>
                  )}
                  {recommendedNextItems(item).length > 0 && (
                    <p className="mt-1 text-xs text-[#8A8D90]">
                      Continue with: {recommendedNextItems(item).map((id) => items.find((entry) => entry.catalog_item_id === id)?.display_name || id).join(', ')}
                    </p>
                  )}
                </div>
                <Link
                  to={catalogLaunchPath(item.category, item.catalog_item_id)}
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
