import { useEffect, useState } from 'react';

interface TimingStats {
  total_provisions: number;
  median_minutes: number;
  p90_minutes: number;
  p99_minutes: number;
  min_minutes: number;
  max_minutes: number;
  by_stage: Record<string, { count: number; avg_minutes: number }>;
  slowest: Array<{ catalog_item: string; avg_minutes: number; count: number; min_minutes: number; max_minutes: number }>;
  fastest: Array<{ catalog_item: string; avg_minutes: number; count: number; min_minutes: number; max_minutes: number }>;
}

interface RecentProvision {
  name: string;
  catalog_item: string;
  stage: string;
  created: string;
  start: string;
  complete: string;
  duration_minutes: number;
  status: string;
}

interface CatalogDetail {
  catalog_item: string;
  stats: { count: number; avg_minutes: number; median_minutes: number; min_minutes: number; max_minutes: number };
  provisions: RecentProvision[];
}

export default function Timing() {
  const [stats, setStats] = useState<TimingStats | null>(null);
  const [recent, setRecent] = useState<RecentProvision[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [detail, setDetail] = useState<CatalogDetail | null>(null);

  useEffect(() => {
    fetch('/api/intelligence/timing', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { stats: {}, recent: [] })
      .then(d => { setStats(d.stats || null); setRecent(d.recent || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const loadDetail = (catalogItem: string) => {
    if (selectedItem === catalogItem) { setSelectedItem(null); setDetail(null); return; }
    setSelectedItem(catalogItem);
    fetch(`/api/intelligence/timing/catalog/${encodeURIComponent(catalogItem)}`, { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : null)
      .then(setDetail)
      .catch(() => setDetail(null));
  };

  const durationColor = (min: number) => min <= 10 ? '#3E8635' : min <= 45 ? '#F0AB00' : '#C9190B';

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Provisioning Timing</h1>
        <p className="text-[#6A6E73] text-sm mt-1">
          Step-by-step provisioning duration from every Babylon AnarchySubject.
          Shows how long each catalog item takes to provision from order to ready.
        </p>
      </div>

      {loading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-16 bg-[#212121] rounded-lg animate-pulse" />)}</div>
      ) : !stats?.total_provisions ? (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-12 text-center">
          <p className="text-[#6A6E73]">No timing data available. Configure BABYLON_KUBECONFIG to pull provisioning history.</p>
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
            {[
              { label: 'Total', value: stats.total_provisions.toLocaleString(), color: '#0071C5' },
              { label: 'Median', value: `${stats.median_minutes}m`, color: durationColor(stats.median_minutes) },
              { label: 'P90', value: `${stats.p90_minutes}m`, color: durationColor(stats.p90_minutes) },
              { label: 'P99', value: `${stats.p99_minutes}m`, color: durationColor(stats.p99_minutes) },
              { label: 'Fastest', value: `${stats.min_minutes}m`, color: '#3E8635' },
              { label: 'Slowest', value: `${stats.max_minutes}m`, color: '#C9190B' },
            ].map(card => (
              <div key={card.label} className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
                <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">{card.label}</p>
                <p className="text-2xl font-bold mt-1" style={{ color: card.color }}>{card.value}</p>
              </div>
            ))}
          </div>

          {/* By stage */}
          {stats.by_stage && Object.keys(stats.by_stage).length > 0 && (
            <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
              <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-3">By Stage</p>
              <div className="flex gap-4">
                {Object.entries(stats.by_stage).map(([stage, data]) => (
                  <div key={stage} className="text-xs">
                    <span className="text-[#6A6E73]">{stage}:</span>{' '}
                    <span className="text-white">{data.count} provisions, avg {data.avg_minutes}m</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-6">
            {/* Slowest */}
            <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
              <p className="text-xs text-[#C9190B] uppercase tracking-wider font-bold mb-3">Slowest Catalog Items</p>
              <div className="space-y-2">
                {stats.slowest.map(item => (
                  <div
                    key={item.catalog_item}
                    className="flex items-center gap-3 text-xs cursor-pointer hover:bg-white/5 rounded px-2 py-1.5 transition"
                    onClick={() => loadDetail(item.catalog_item)}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-white truncate">{item.catalog_item}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="w-20 h-1.5 bg-[#333] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{
                          width: `${Math.min(100, (item.avg_minutes / stats.max_minutes) * 100)}%`,
                          backgroundColor: durationColor(item.avg_minutes),
                        }} />
                      </div>
                      <span className="font-mono w-14 text-right" style={{ color: durationColor(item.avg_minutes) }}>
                        {item.avg_minutes}m
                      </span>
                      <span className="text-[#6A6E73] w-8 text-right">({item.count})</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Fastest */}
            <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
              <p className="text-xs text-[#3E8635] uppercase tracking-wider font-bold mb-3">Fastest Catalog Items</p>
              <div className="space-y-2">
                {stats.fastest.map(item => (
                  <div
                    key={item.catalog_item}
                    className="flex items-center gap-3 text-xs cursor-pointer hover:bg-white/5 rounded px-2 py-1.5 transition"
                    onClick={() => loadDetail(item.catalog_item)}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-white truncate">{item.catalog_item}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="w-20 h-1.5 bg-[#333] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{
                          width: `${Math.min(100, (item.avg_minutes / 30) * 100)}%`,
                          backgroundColor: durationColor(item.avg_minutes),
                        }} />
                      </div>
                      <span className="font-mono w-14 text-right" style={{ color: durationColor(item.avg_minutes) }}>
                        {item.avg_minutes}m
                      </span>
                      <span className="text-[#6A6E73] w-8 text-right">({item.count})</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Catalog item detail */}
          {selectedItem && detail && (
            <div className="bg-[#212121] border border-[#0071C5] rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs text-[#0071C5] uppercase tracking-wider font-bold">{selectedItem}</p>
                <button onClick={() => { setSelectedItem(null); setDetail(null); }} className="text-xs text-[#6A6E73] hover:text-white">Close</button>
              </div>
              {detail.stats && (
                <div className="grid grid-cols-5 gap-4 mb-4 text-xs">
                  <div><span className="text-[#6A6E73] block">Count</span><span className="text-white font-medium">{detail.stats.count}</span></div>
                  <div><span className="text-[#6A6E73] block">Average</span><span className="text-white font-medium">{detail.stats.avg_minutes}m</span></div>
                  <div><span className="text-[#6A6E73] block">Median</span><span className="text-white">{detail.stats.median_minutes}m</span></div>
                  <div><span className="text-[#6A6E73] block">Fastest</span><span className="text-[#3E8635]">{detail.stats.min_minutes}m</span></div>
                  <div><span className="text-[#6A6E73] block">Slowest</span><span className="text-[#C9190B]">{detail.stats.max_minutes}m</span></div>
                </div>
              )}
              <div className="space-y-1">
                {detail.provisions.slice(0, 15).map(p => (
                  <div key={p.name} className="flex items-center gap-3 text-xs py-1 border-b border-[#1a1a1a] last:border-0">
                    <span className="text-[#6A6E73] font-mono w-28">{p.created?.slice(0, 16).replace('T', ' ')}</span>
                    <span className="text-[#6A6E73] w-10">{p.stage}</span>
                    <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{
                        width: `${Math.min(100, (p.duration_minutes / 120) * 100)}%`,
                        backgroundColor: durationColor(p.duration_minutes),
                      }} />
                    </div>
                    <span className="font-mono w-12 text-right" style={{ color: durationColor(p.duration_minutes) }}>
                      {p.duration_minutes}m
                    </span>
                    <span className={`w-16 text-right ${p.status === 'successful' ? 'text-[#3E8635]' : 'text-[#C9190B]'}`}>
                      {p.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent provisions */}
          <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
            <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-3">Recent Provisions</p>
            <div className="space-y-1">
              {recent.slice().reverse().map(p => (
                <div
                  key={p.name}
                  className="flex items-center gap-3 text-xs py-1.5 border-b border-[#1a1a1a] last:border-0 cursor-pointer hover:bg-white/5 rounded transition"
                  onClick={() => loadDetail(p.catalog_item)}
                >
                  <span className="text-[#6A6E73] font-mono w-28">{p.created?.slice(0, 16).replace('T', ' ')}</span>
                  <span className="text-white flex-1 truncate">{p.catalog_item}</span>
                  <span className="text-[#6A6E73] w-10">{p.stage}</span>
                  <span className="font-mono w-12 text-right" style={{ color: durationColor(p.duration_minutes) }}>
                    {p.duration_minutes}m
                  </span>
                  <span className={`w-16 text-right ${p.status === 'successful' ? 'text-[#3E8635]' : 'text-[#C9190B]'}`}>
                    {p.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
