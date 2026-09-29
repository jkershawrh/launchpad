import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';
import { catalogLaunchPath } from '../catalogNavigation';
import { LEARNING_STAGE } from '../catalogLearning';
import { LEARNING_TRACKS, type LearningTrackEntry } from '../learningTracks';

const STATE_STYLE = {
  available: 'border-[#3E8635]/60 bg-[#3E8635]/10 text-[#BDEFA6]',
  draft: 'border-[#F0AB00]/60 bg-[#F0AB00]/10 text-[#F8C95E]',
  planned: 'border-[#555] bg-[#262626] text-[#A3A3A3]',
} as const;

function effectiveState(entry: LearningTrackEntry, catalog?: CatalogItem) {
  if (entry.lifecycle !== 'active') return entry.lifecycle;
  return catalog?.status === 'active' ? 'available' : 'draft';
}

export default function LearningPaths() {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [catalogError, setCatalogError] = useState(false);

  useEffect(() => {
    api.listCatalog()
      .then(setCatalog)
      .catch(() => setCatalogError(true));
  }, []);

  const byId = useMemo(
    () => new Map(catalog.map((item) => [item.catalog_item_id, item])),
    [catalog],
  );

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-6 py-8 lg:px-8">
      <header className="border-b border-[#333] pb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#73BCF7]">Learn · build · operate · qualify</p>
        <h1 className="mt-1 text-3xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>AI learning paths</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-[#A3A3A3]">Choose a technical progression, see what is available now, and understand what is coming next. Only active catalog releases with current certification can be ordered.</p>
      </header>

      {catalogError && (
        <div role="alert" className="rounded border border-[#F0AB00]/60 bg-[#F0AB00]/10 p-4 text-sm text-[#F8C95E]">
          Live catalog status is unavailable. Learning paths remain visible, but ordering is disabled until status can be verified.
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-3">
        {LEARNING_TRACKS.map((track) => (
          <section key={track.id} className="overflow-hidden rounded-lg border border-[#3b3b3b] bg-[#1b1b1b]" aria-labelledby={`track-${track.id}`}>
            <div className="border-b border-[#333] bg-[#212121] p-5">
              <h2 id={`track-${track.id}`} className="text-xl font-semibold text-white">{track.label}</h2>
              <p className="mt-2 min-h-10 text-xs leading-5 text-[#8A8D90]">{track.description}</p>
            </div>
            <ol className="space-y-0 p-4">
              {track.entries.map((entry) => {
                const item = entry.catalogId ? byId.get(entry.catalogId) : undefined;
                const state = effectiveState(entry, item);
                return (
                  <li key={`${track.id}-${entry.level}`} className="relative border-l border-[#444] pb-5 pl-6 last:pb-1">
                    <span className="absolute -left-3 top-0 flex h-6 w-6 items-center justify-center rounded-full border border-[#666] bg-[#151515] font-mono text-[10px] text-white">{entry.level[0]}</span>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-[#73BCF7]">{entry.level} · {LEARNING_STAGE[entry.level]}</p>
                        <h3 className="mt-1 text-sm font-semibold leading-5 text-white">{entry.title}</h3>
                      </div>
                      <span className={`shrink-0 rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${STATE_STYLE[state]}`}>
                        {state}
                      </span>
                    </div>
                    {state === 'available' && item && (
                      <Link className="mt-3 inline-block text-xs font-semibold text-[#73BCF7] hover:underline" to={catalogLaunchPath(item.category, item.catalog_item_id)}>
                        Order this lab →
                      </Link>
                    )}
                    {state === 'draft' && <p className="mt-2 text-[11px] text-[#8A8D90]">Certification or activation is still required.</p>}
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </div>

      <section className="rounded-lg border border-[#333] bg-[#212121] p-6">
        <div className="grid gap-5 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#F8C95E]">Sales enablement</p>
            <h2 className="mt-1 text-xl font-semibold text-white">Sales tracks remain a separate persona layer</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#A3A3A3]">Sales journeys will reuse certified technical labs with role-specific outcomes, talk tracks, evidence, and handoff guidance. Their titles and audience mapping are intentionally not invented here; they remain pending product-owner definition.</p>
          </div>
          <Link to="/catalog" className="rounded bg-[#EE0000] px-5 py-3 text-center text-sm font-semibold text-white hover:bg-[#CC0000]">Browse orderable labs</Link>
        </div>
      </section>
    </div>
  );
}
