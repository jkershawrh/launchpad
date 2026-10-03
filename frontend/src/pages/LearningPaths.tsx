import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';
import { catalogLaunchPath } from '../catalogNavigation';
import { LEARNING_STAGE } from '../catalogLearning';
import { LEARNING_TRACKS, type LearningTrackEntry } from '../learningTracks';
import { SALES_ENTRIES, salesEntryUrl } from '../salesEntries';

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
  const currentHostname = typeof window === 'undefined' ? '' : window.location.hostname;

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

      <section className="rounded-lg border border-[#333] bg-[#212121] p-6" aria-labelledby="sales-entry-heading">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#F8C95E]">Sales enablement</p>
        <h2 id="sales-entry-heading" className="mt-1 text-xl font-semibold text-white">Start with the customer conversation</h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-[#A3A3A3]">These short presentation experiences frame the opportunity before a learner enters a certified technical lab. Exploring a story does not provision an environment or consume a seat.</p>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {SALES_ENTRIES.map((entry) => {
            const storyUrl = salesEntryUrl(entry.routeName, currentHostname);
            const labPath = entry.labCatalogId
              ? `/request?catalog_item=${encodeURIComponent(entry.labCatalogId)}`
              : '/paths';
            return (
              <article key={entry.id} className="rounded border border-[#444] bg-[#181818] p-5">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#73BCF7]">Sales entry · no environment provisioned</p>
                <h3 className="mt-2 text-base font-semibold leading-6 text-white">{entry.title}</h3>
                <p className="mt-2 text-xs leading-5 text-[#A3A3A3]">{entry.description}</p>
                <div className="mt-4 flex flex-wrap gap-3">
                  {storyUrl && (
                    <a href={storyUrl} target="_blank" rel="noreferrer" className="rounded bg-[#0066CC] px-4 py-2 text-xs font-semibold text-white hover:bg-[#004B95]">
                      Explore story
                    </a>
                  )}
                  <Link to={labPath} className="rounded border border-[#6A6E73] px-4 py-2 text-xs font-semibold text-white hover:border-[#A3A3A3]">
                    {entry.labLabel} →
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
