import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import { catalogLaunchPath } from '../catalogNavigation';
import {
  LEARNING_LEVELS,
  LEARNING_STAGE,
  SOLUTION_FAMILIES,
  SOLUTION_FAMILY_LABEL,
  groupBySolutionFamily,
  learningLevel,
  prerequisites,
  recommendedNextItems,
  solutionFamily,
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
  const [query, setQuery] = useState('');
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = searchParams.get('category') || 'all';
  const levelFilter = searchParams.get('level') || 'all';
  const familyFilter = searchParams.get('family') || 'all';

  useEffect(() => {
    api.listCatalog().then((data) => {
      setItems(participantCatalog(data));
      setLoading(false);
    });
  }, []);

  const normalizedQuery = query.trim().toLowerCase();
  const filtered = sortByLearningProgression(items.filter((item) => {
    const searchable = [
      item.display_name,
      item.description,
      item.catalog_item_id,
      SOLUTION_FAMILY_LABEL[solutionFamily(item) as keyof typeof SOLUTION_FAMILY_LABEL] || '',
      ...item.required_capabilities,
    ].join(' ').toLowerCase();
    return (filter === 'all' || item.category === filter)
      && (levelFilter === 'all' || learningLevel(item) === levelFilter)
      && (familyFilter === 'all' || solutionFamily(item) === familyFilter)
      && (!normalizedQuery || searchable.includes(normalizedQuery));
  }));
  const sections = groupBySolutionFamily(filtered);

  const updateFilter = (key: 'category' | 'level' | 'family', value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === 'all') next.delete(key);
    else next.set(key, value);
    setSearchParams(next);
  };

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[#333] pb-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#73BCF7]">Order an environment</p>
          <h1 className="mt-1 text-3xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>AI learning catalog</h1>
          <p className="mt-2 max-w-2xl text-sm text-[#8A8D90]">Choose by how you will use AI, then follow the 001–501 progression within that solution family. Every card below is currently available to order.</p>
        </div>
        <div className="rounded-lg border border-[#3c3f42] bg-[#212121] px-4 py-3 text-right">
          <strong className="block text-2xl text-white">{items.length}</strong>
          <span className="text-xs uppercase tracking-wider text-[#8A8D90]">Available items</span>
        </div>
      </div>

      <div className="space-y-4 rounded-lg border border-[#333] bg-[#1b1b1b] p-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(240px,1fr)_auto] lg:items-center">
          <label className="relative block">
            <span className="sr-only">Search catalog</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search labs, skills, or capabilities…" className="w-full rounded border border-[#4b4b4b] bg-[#151515] px-4 py-2.5 text-sm text-white placeholder:text-[#6A6E73] focus:border-[#73BCF7] focus:outline-none" />
          </label>
          <div className="flex flex-wrap gap-2">
            {['all', 'quick_start', 'guided_build', 'open_sandbox'].map((cat) => (
              <button key={cat} onClick={() => updateFilter('category', cat)} className={`rounded px-3 py-2 text-xs font-medium transition ${filter === cat ? 'bg-white/15 text-white' : 'text-[#8A8D90] hover:bg-white/10 hover:text-white'}`}>
                {cat === 'all' ? 'All types' : CATEGORY_LABELS[cat]}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-[#333] pt-4">
          <span className="mr-1 text-xs font-medium uppercase tracking-wider text-[#8A8D90]">Use</span>
          {['all', ...SOLUTION_FAMILIES.filter((family) => family !== 'platform_validation')].map((family) => (
            <button key={family} onClick={() => updateFilter('family', family)} className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${familyFilter === family ? 'bg-[#3E8635] text-white' : 'bg-[#212121] text-[#8A8D90] hover:bg-white/10 hover:text-white'}`}>
              {family === 'all' ? 'All uses' : SOLUTION_FAMILY_LABEL[family as keyof typeof SOLUTION_FAMILY_LABEL]}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-[#333] pt-4">
          <span className="mr-1 text-xs font-medium uppercase tracking-wider text-[#8A8D90]">Level</span>
          {['all', ...LEARNING_LEVELS].map((level) => (
            <button key={level} onClick={() => updateFilter('level', level)} className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${levelFilter === level ? 'bg-[#0068B5] text-white' : 'bg-[#212121] text-[#8A8D90] hover:bg-white/10 hover:text-white'}`}>
              {level === 'all' ? 'All' : `${level} · ${LEARNING_STAGE[level as keyof typeof LEARNING_STAGE]}`}
            </button>
          ))}
          <span className="ml-auto text-xs text-[#6A6E73]">Showing {filtered.length} of {items.length}</span>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-20 bg-[#212121] rounded-lg animate-pulse" />)}
        </div>
      ) : (
        sections.length === 0 ? (
          <div className="rounded-lg border border-dashed border-[#4b4b4b] py-14 text-center text-sm text-[#8A8D90]">No available catalog items match these filters.</div>
        ) : (
          <div className="space-y-9">
            {sections.map((section) => (
              <section key={section.family} aria-labelledby={`catalog-family-${section.family}`}>
                <div className="mb-4 flex items-end justify-between gap-4 border-b border-[#333] pb-3">
                  <div className="flex items-center gap-3">
                    <span className="rounded bg-[#3E8635] px-2.5 py-1 text-sm font-bold text-white">{section.family === 'other' ? 'More' : 'Use'}</span>
                    <div><h2 id={`catalog-family-${section.family}`} className="text-lg font-semibold text-white">{section.label}</h2><p className="text-xs text-[#8A8D90]">Ordered by learning level from exploration through scale.</p></div>
                  </div>
                  <span className="text-xs text-[#6A6E73]">{section.items.length} available</span>
                </div>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {section.items.map((item) => (
                    <article key={item.catalog_item_id} className="flex min-h-[285px] flex-col rounded-lg border border-[#353535] bg-[#212121] p-5 transition hover:-translate-y-0.5 hover:border-[#666]" style={{ borderTopWidth: '3px', borderTopColor: CATEGORY_BORDER[item.category] || '#333' }}>
                      <div className="mb-3 flex flex-wrap items-center gap-2"><StatusBadge status={item.category} /><span className="rounded bg-[#0068B5]/20 px-2 py-0.5 text-[11px] font-semibold text-[#73BCF7]">{learningLevel(item)} · {learningLevel(item) ? LEARNING_STAGE[learningLevel(item)!] : 'Unclassified'}</span><span className="text-xs text-[#6A6E73]">v{item.version}</span></div>
                      <h3 className="text-base font-semibold leading-snug text-white">{item.display_name}</h3>
                      <p className="mt-2 line-clamp-4 text-xs leading-5 text-[#8A8D90]">{item.description}</p>
                      <div className="mt-4 flex flex-wrap gap-1">{item.required_capabilities.slice(0, 4).map((cap) => <span key={cap} className="rounded bg-[#171717] px-2 py-0.5 text-[11px] text-[#8A8D90]">{cap}</span>)}</div>
                      <div className="mt-auto pt-5">
                        {prerequisites(item).length > 0 && <p className="mb-2 text-[11px] text-[#8A8D90]">Builds on: {prerequisites(item).map((id) => items.find((entry) => entry.catalog_item_id === id)?.display_name || id).join(', ')}</p>}
                        <Link to={catalogLaunchPath(item.category, item.catalog_item_id)} className="block w-full rounded px-4 py-2.5 text-center text-xs font-semibold text-white transition hover:brightness-110" style={{ backgroundColor: 'var(--brand-primary)' }}>
                          {item.category === 'open_sandbox' ? 'Configure environment' : 'Order this lab'}
                        </Link>
                        {recommendedNextItems(item).length > 0 && <p className="mt-2 text-center text-[11px] text-[#6A6E73]">Next: {recommendedNextItems(item).map((id) => items.find((entry) => entry.catalog_item_id === id)?.display_name || id).join(', ')}</p>}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )
      )}
    </div>
  );
}
