import type { OrchestrationDecision } from '../api/types';

const WORKLOAD_COLORS: Record<string, string> = {
  gpu_inference: '#0068B5',
  training: '#E67E22',
  cpu_inference: '#3E8635',
  rag_pipeline: '#6A3D9A',
  agent: '#0068B5',
  mixed: '#E67E22',
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
      <div className="flex-1 h-2 bg-[#F0F0F0] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-mono font-medium" style={{ color }}>{pct}%</span>
    </div>
  );
}

export default function DecisionInsight({ decision }: { decision: OrchestrationDecision | null }) {
  if (!decision) return null;

  const wp = decision.workload_profile;
  const workloadColor = wp ? WORKLOAD_COLORS[wp.workload_type] || '#6A6E73' : '#6A6E73';
  const workloadLabel = wp ? WORKLOAD_LABELS[wp.workload_type] || wp.workload_type : 'Unknown';

  return (
    <div className="bg-white rounded-lg border p-6 mb-6">
      <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Placement Decision</h2>

      <div className="grid md:grid-cols-3 gap-6">
        <div>
          <p className="text-xs text-[#6A6E73] uppercase font-medium mb-2">Workload</p>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-medium text-white px-2 py-0.5 rounded" style={{ backgroundColor: workloadColor }}>
              {workloadLabel}
            </span>
            {wp?.gpu_required && (
              <span className="text-xs bg-[#E67E22] text-white px-2 py-0.5 rounded">GPU</span>
            )}
          </div>
          {wp && (
            <dl className="space-y-1 text-xs">
              <div className="flex justify-between"><dt className="text-[#6A6E73]">Compute</dt><dd className="text-[#151515] font-medium">{wp.compute_intensity}</dd></div>
              <div className="flex justify-between"><dt className="text-[#6A6E73]">Memory</dt><dd className="text-[#151515] font-medium">{wp.memory_intensity}</dd></div>
            </dl>
          )}
        </div>

        <div>
          <p className="text-xs text-[#6A6E73] uppercase font-medium mb-2">Hardware</p>
          <p className="text-lg font-bold text-[#151515] mb-1">{decision.recommended_hardware}</p>
          <p className="text-xs text-[#6A6E73]">Quota: {decision.recommended_quota}</p>
        </div>

        <div>
          <p className="text-xs text-[#6A6E73] uppercase font-medium mb-2">Cluster</p>
          {decision.recommended_cluster ? (
            <p className="text-lg font-bold text-[#151515] mb-2">{decision.recommended_cluster}</p>
          ) : (
            <p className="text-sm text-[#6A6E73] italic mb-2">Auto-selected by pool</p>
          )}
          <p className="text-xs text-[#6A6E73] mb-2">Confidence:</p>
          <ConfidenceBar value={decision.confidence} />
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-[#F0F0F0]">
        <p className="text-sm text-[#151515] mb-2">{decision.rationale}</p>
        <div className="flex flex-wrap gap-1">
          {decision.signals_used.map((s) => (
            <span key={s} className="text-xs bg-[#F0F0F0] text-[#6A6E73] px-2 py-0.5 rounded">{s.replace(/_/g, ' ')}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
