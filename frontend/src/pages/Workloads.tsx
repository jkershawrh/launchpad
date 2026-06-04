import { useEffect, useState } from 'react';

interface ClassifiedItem {
  catalog_item_id: string;
  display_name: string;
  description: string;
  category: string;
  workload_profile?: {
    workload_type: string;
    compute_intensity: string;
    memory_intensity: string;
    gpu_required: boolean;
    gpu_mode: string;
    io_pattern: string;
    resource_profile: string;
    confidence: number;
    classification_source: string;
  };
  recommended_hardware: string;
  recommended_quota: string;
  hardware_matches?: Array<{
    hardware_profile: string;
    score: number;
    reasons: string[];
  }>;
}

const TYPE_COLORS: Record<string, string> = {
  gpu_inference: '#0071C5', cpu_inference: '#3E8635', training: '#F0AB00',
  rag_pipeline: '#6A3D9A', agent: '#0071C5', mixed: '#F0AB00', lightweight: '#6A6E73',
  virtualization: '#E67E22', automation: '#C9190B', platform_ops: '#0071C5',
  developer: '#3E8635', security: '#C9190B', edge: '#F0AB00',
  infrastructure: '#6A6E73', cloud_env: '#0071C5', integration: '#3E8635',
  sandbox: '#6A6E73', workshop: '#F0AB00',
};
const TYPE_LABELS: Record<string, string> = {
  gpu_inference: 'GPU Inference', cpu_inference: 'CPU Inference', training: 'Training',
  rag_pipeline: 'RAG Pipeline', agent: 'Agent', mixed: 'Mixed', lightweight: 'Lightweight',
  virtualization: 'Virtualization', automation: 'Automation', platform_ops: 'Platform Ops',
  developer: 'Developer', security: 'Security', edge: 'Edge',
  infrastructure: 'Infrastructure', cloud_env: 'Cloud', integration: 'Integration',
  sandbox: 'Sandbox', workshop: 'Workshop',
};
const SOURCE_COLORS: Record<string, string> = {
  catalog_metadata: '#0071C5', rules: '#3E8635', llm: '#F0AB00', history: '#6A3D9A',
};

export default function Workloads() {
  const [items, setItems] = useState<ClassifiedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [expandedItem, setExpandedItem] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/intelligence/classifications', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => { setItems(d.items || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const workloadTypes = ['all', ...new Set(
    items.map(i => i.workload_profile?.workload_type).filter(Boolean)
  )] as string[];

  const classifiedCount = items.filter(i => i.workload_profile).length;

  const filtered = items.filter(i => {
    if (filter !== 'all' && i.workload_profile?.workload_type !== filter) return false;
    if (search) {
      const q = search.toLowerCase();
      return i.display_name.toLowerCase().includes(q) || i.catalog_item_id.toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Workload Classification</h1>
        <p className="text-[#6A6E73] text-sm mt-1">
          {classifiedCount} of {items.length} catalog items classified. Click any item to see workload profile,
          hardware match ranking, and classification details.
        </p>
      </div>

      <div className="flex gap-3 flex-wrap items-center">
        <input
          type="text"
          placeholder="Search catalog items..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="bg-[#1a1a1a] border border-[#333] rounded px-3 py-1.5 text-sm text-white w-64 placeholder-[#6A6E73]"
        />
        {workloadTypes.map(t => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1.5 rounded text-xs font-medium transition ${
              filter === t ? 'bg-white/15 text-white' : 'text-[#6A6E73] hover:text-white hover:bg-white/10'
            }`}
          >
            {t === 'all' ? `All (${items.length})` : `${TYPE_LABELS[t] || t} (${items.filter(i => i.workload_profile?.workload_type === t).length})`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[1,2,3,4].map(i => <div key={i} className="h-14 bg-[#212121] rounded-lg animate-pulse" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-12 text-center">
          <p className="text-[#6A6E73]">{search ? 'No items match your search.' : 'No items to display.'}</p>
        </div>
      ) : (
        <div className="space-y-1">
          {filtered.map(item => {
            const wp = item.workload_profile;
            const typeColor = wp ? TYPE_COLORS[wp.workload_type] || '#6A6E73' : '#333';
            const isExpanded = expandedItem === item.catalog_item_id;
            return (
              <div
                key={item.catalog_item_id}
                className={`bg-[#212121] border rounded-lg transition cursor-pointer ${isExpanded ? 'border-[#0071C5]' : 'border-[#2e2e2e] hover:border-[#555]'}`}
                style={{ borderLeftWidth: '3px', borderLeftColor: typeColor }}
                onClick={() => setExpandedItem(isExpanded ? null : item.catalog_item_id)}
              >
                <div className="flex items-center justify-between px-4 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-white truncate">{item.display_name}</p>
                    <p className="text-xs text-[#6A6E73] font-mono truncate">{item.catalog_item_id}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-3">
                    {wp?.classification_source && (
                      <span className="text-xs px-1.5 py-0.5 rounded text-white hidden md:inline" style={{ backgroundColor: SOURCE_COLORS[wp.classification_source] || '#6A6E73' }}>
                        {wp.classification_source.replace(/_/g, ' ')}
                      </span>
                    )}
                    {wp ? (
                      <span className="text-xs font-semibold text-white px-2 py-0.5 rounded" style={{ backgroundColor: typeColor }}>
                        {TYPE_LABELS[wp.workload_type] || wp.workload_type}
                      </span>
                    ) : (
                      <span className="text-xs text-[#6A6E73] px-2 py-0.5 rounded bg-[#1a1a1a]">unclassified</span>
                    )}
                    <span className="text-xs text-[#6A6E73] w-24 text-right hidden sm:inline">{item.recommended_hardware}</span>
                    <span className="text-[#6A6E73] text-xs">{isExpanded ? '▲' : '▼'}</span>
                  </div>
                </div>

                {isExpanded && (
                  <div className="px-4 pb-4 border-t border-[#333] pt-3">
                    {item.description && <p className="text-xs text-[#6A6E73] mb-3">{item.description}</p>}
                    {wp ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-xs">
                          <div><span className="text-[#6A6E73] block">Compute</span><span className="text-white">{wp.compute_intensity}</span></div>
                          <div><span className="text-[#6A6E73] block">Memory</span><span className="text-white">{wp.memory_intensity}</span></div>
                          <div><span className="text-[#6A6E73] block">GPU</span><span className={wp.gpu_required ? 'text-[#F0AB00]' : 'text-[#6A6E73]'}>{wp.gpu_required ? wp.gpu_mode : 'none'}</span></div>
                          <div><span className="text-[#6A6E73] block">I/O</span><span className="text-white">{wp.io_pattern}</span></div>
                          <div><span className="text-[#6A6E73] block">Resource</span><span className="text-white">{wp.resource_profile?.replace(/_/g, ' ') || '—'}</span></div>
                          <div><span className="text-[#6A6E73] block">Hardware</span><span className="text-white font-medium">{item.recommended_hardware}</span></div>
                        </div>
                        <div className="flex items-center gap-2 text-xs">
                          <span className="text-[#6A6E73] w-16">Confidence</span>
                          <div className="flex-1 h-1 bg-[#333] rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${Math.round(wp.confidence * 100)}%`, backgroundColor: wp.confidence >= 0.8 ? '#3E8635' : '#F0AB00' }} />
                          </div>
                          <span className="text-[#6A6E73] font-mono w-8 text-right">{Math.round(wp.confidence * 100)}%</span>
                        </div>
                        {item.hardware_matches && item.hardware_matches.length > 0 && (
                          <div>
                            <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-2">Hardware Match Ranking</p>
                            <div className="space-y-1">
                              {item.hardware_matches.map((m, i) => (
                                <div key={m.hardware_profile} className={`flex items-center gap-3 text-xs ${i === 0 ? 'text-white' : 'text-[#6A6E73]'}`}>
                                  <span className="w-4 text-right font-mono">{i + 1}.</span>
                                  <span className="w-28 font-medium">{m.hardware_profile}</span>
                                  <div className="flex-1 h-1 bg-[#333] rounded-full overflow-hidden">
                                    <div className="h-full rounded-full" style={{ width: `${m.score}%`, backgroundColor: i === 0 ? '#0071C5' : '#444' }} />
                                  </div>
                                  <span className="font-mono w-8 text-right">{Math.round(m.score)}</span>
                                </div>
                              ))}
                            </div>
                            {item.hardware_matches[0]?.reasons?.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-2">
                                {item.hardware_matches[0].reasons.map((r, i) => (
                                  <span key={i} className="text-xs bg-[#1a1a1a] text-[#6A6E73] px-2 py-0.5 rounded">{r}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-[#6A6E73]">No classification available — this item lacks hardware profile and capability metadata.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
