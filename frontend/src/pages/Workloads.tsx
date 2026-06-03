import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';

interface Classification {
  workload_profile?: {
    workload_type: string;
    compute_intensity: string;
    memory_intensity: string;
    gpu_required: boolean;
    gpu_mode: string;
    io_pattern: string;
    confidence: number;
  };
  recommended_hardware: string;
  recommended_quota: string;
}

const TYPE_COLORS: Record<string, string> = {
  gpu_inference: '#0071C5',
  cpu_inference: '#3E8635',
  training: '#F0AB00',
  rag_pipeline: '#6A3D9A',
  agent: '#0071C5',
  mixed: '#F0AB00',
  lightweight: '#6A6E73',
};

const TYPE_LABELS: Record<string, string> = {
  gpu_inference: 'GPU Inference',
  cpu_inference: 'CPU Inference',
  training: 'Training',
  rag_pipeline: 'RAG Pipeline',
  agent: 'Agent',
  mixed: 'Mixed',
  lightweight: 'Lightweight',
};

export default function Workloads() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [classifications, setClassifications] = useState<Record<string, Classification>>({});
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    api.listCatalog().then(data => {
      setItems(data);
      data.forEach(item => {
        fetch('/api/intelligence/simulate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ catalog_item_id: item.catalog_item_id, tenant_id: 'classify' }),
        })
          .then(r => r.ok ? r.json() : null)
          .then(d => { if (d) setClassifications(prev => ({ ...prev, [item.catalog_item_id]: d })); })
          .catch(() => null);
      });
    }).catch(() => null);
  }, []);

  const workloadTypes = ['all', ...new Set(
    Object.values(classifications).map(c => c.workload_profile?.workload_type).filter(Boolean)
  )] as string[];

  const filtered = filter === 'all'
    ? items
    : items.filter(i => classifications[i.catalog_item_id]?.workload_profile?.workload_type === filter);

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Workload Classification</h1>
        <p className="text-[#6A6E73] text-sm mt-1">
          The classifier analyzes each catalog item's capabilities, hardware requirements, and metadata
          to determine its workload type and match it to optimal hardware.
        </p>
      </div>

      {/* Type filters */}
      <div className="flex gap-2 flex-wrap">
        {workloadTypes.map(t => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1.5 rounded text-xs font-medium transition ${
              filter === t ? 'bg-white/15 text-white' : 'text-[#6A6E73] hover:text-white hover:bg-white/10'
            }`}
          >
            {t === 'all' ? 'All' : TYPE_LABELS[t] || t}
          </button>
        ))}
      </div>

      {/* Workload cards */}
      {items.length === 0 ? (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-12 text-center">
          <p className="text-[#6A6E73]">Loading catalog...</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {filtered.map(item => {
            const cls = classifications[item.catalog_item_id];
            const wp = cls?.workload_profile;
            const typeColor = wp ? TYPE_COLORS[wp.workload_type] || '#6A6E73' : '#333';

            return (
              <div
                key={item.catalog_item_id}
                className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4 hover:border-[#555] transition"
                style={{ borderLeftWidth: '3px', borderLeftColor: typeColor }}
              >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h3 className="text-sm font-medium text-white">{item.display_name}</h3>
                    <p className="text-xs text-[#6A6E73] font-mono mt-0.5">{item.catalog_item_id}</p>
                  </div>
                  {wp && (
                    <span className="text-xs font-semibold text-white px-2 py-0.5 rounded shrink-0" style={{ backgroundColor: typeColor }}>
                      {TYPE_LABELS[wp.workload_type] || wp.workload_type}
                    </span>
                  )}
                </div>

                {wp ? (
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-3 text-xs">
                    <div className="flex justify-between">
                      <span className="text-[#6A6E73]">Compute</span>
                      <span className="text-white">{wp.compute_intensity}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#6A6E73]">Memory</span>
                      <span className="text-white">{wp.memory_intensity}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#6A6E73]">GPU</span>
                      <span className={wp.gpu_required ? 'text-[#F0AB00]' : 'text-[#6A6E73]'}>
                        {wp.gpu_required ? wp.gpu_mode : 'none'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#6A6E73]">I/O</span>
                      <span className="text-white">{wp.io_pattern}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#6A6E73]">Hardware</span>
                      <span className="text-white font-medium">{cls?.recommended_hardware}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#6A6E73]">Quota</span>
                      <span className="text-white">{cls?.recommended_quota}</span>
                    </div>
                    <div className="col-span-2 flex items-center gap-2 mt-1">
                      <span className="text-[#6A6E73]">Confidence</span>
                      <div className="flex-1 h-1 bg-[#333] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{
                          width: `${Math.round(wp.confidence * 100)}%`,
                          backgroundColor: wp.confidence >= 0.8 ? '#3E8635' : '#F0AB00',
                        }} />
                      </div>
                      <span className="text-[#6A6E73] font-mono">{Math.round(wp.confidence * 100)}%</span>
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 text-xs text-[#6A6E73]">
                    {cls === undefined ? 'Classifying...' : 'Enable ORCHESTRATION_BRAIN_ENABLED to see classification.'}
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
