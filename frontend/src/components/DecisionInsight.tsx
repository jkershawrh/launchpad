import type { OrchestrationDecision } from '../api/types';

const WORKLOAD_COLORS: Record<string, string> = {
  gpu_inference: '#0071C5',
  training: '#F0AB00',
  cpu_inference: '#3E8635',
  rag_pipeline: '#6A3D9A',
  agent: '#0071C5',
  mixed: '#F0AB00',
  lightweight: '#6A6E73',
};

const WORKLOAD_LABELS: Record<string, string> = {
  gpu_inference: 'GPU Inference',
  training: 'Training',
  cpu_inference: 'CPU Inference',
  rag_pipeline: 'RAG Pipeline',
  agent: 'Agent',
  mixed: 'Mixed Workload',
  lightweight: 'Lightweight',
};

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? '#3E8635' : pct >= 40 ? '#F0AB00' : '#C9190B';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-mono" style={{ color }}>{pct}%</span>
    </div>
  );
}

export default function DecisionInsight({ decision }: { decision: OrchestrationDecision | null }) {
  if (!decision) return null;

  const wp = decision.workload_profile;
  const workloadColor = wp ? WORKLOAD_COLORS[wp.workload_type] || '#6A6E73' : '#6A6E73';
  const workloadLabel = wp ? WORKLOAD_LABELS[wp.workload_type] || wp.workload_type : 'Unknown';

  return (
    <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4 mb-6">
      <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Placement Decision</p>

      <div className="grid md:grid-cols-3 gap-6">
        <div>
          <p className="text-xs text-[#6A6E73] mb-2">Workload</p>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-semibold text-white px-2 py-0.5 rounded" style={{ backgroundColor: workloadColor }}>
              {workloadLabel}
            </span>
            {wp?.gpu_required && (
              <span className="text-xs font-semibold text-white px-2 py-0.5 rounded bg-[#F0AB00]">GPU</span>
            )}
          </div>
          {wp && (
            <dl className="space-y-1 text-xs">
              <div className="flex justify-between"><dt className="text-[#6A6E73]">Compute</dt><dd className="text-white">{wp.compute_intensity}</dd></div>
              <div className="flex justify-between"><dt className="text-[#6A6E73]">Memory</dt><dd className="text-white">{wp.memory_intensity}</dd></div>
              <div className="flex justify-between"><dt className="text-[#6A6E73]">I/O</dt><dd className="text-white">{wp.io_pattern}</dd></div>
            </dl>
          )}
        </div>

        <div>
          <p className="text-xs text-[#6A6E73] mb-2">Hardware</p>
          <p className="text-lg font-bold text-white mb-1">{decision.recommended_hardware}</p>
          <p className="text-xs text-[#6A6E73]">Quota: {decision.recommended_quota}</p>
          {decision.fallback_chain.length > 0 && (
            <div className="mt-2">
              <p className="text-xs text-[#6A6E73] mb-1">Fallback:</p>
              <div className="flex flex-wrap gap-1">
                {decision.fallback_chain.map(c => (
                  <span key={c} className="text-xs bg-[#1a1a1a] text-[#6A6E73] px-2 py-0.5 rounded">{c}</span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div>
          <p className="text-xs text-[#6A6E73] mb-2">Cluster</p>
          {decision.recommended_cluster ? (
            <p className="text-lg font-bold text-white mb-2">{decision.recommended_cluster}</p>
          ) : (
            <p className="text-sm text-[#6A6E73] italic mb-2">Auto-selected</p>
          )}
          <p className="text-xs text-[#6A6E73] mb-2">Confidence:</p>
          <ConfidenceBar value={decision.confidence} />
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-[#333]">
        <p className="text-sm text-[#e0e0e0] mb-2">{decision.rationale}</p>
        <div className="flex flex-wrap gap-1">
          {decision.signals_used.map(s => (
            <span key={s} className="text-xs bg-[#1a1a1a] text-[#6A6E73] px-2 py-0.5 rounded">{s.replace(/_/g, ' ')}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
