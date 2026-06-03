import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { LabSession, OrchestrationDecision } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import DecisionInsight from '../components/DecisionInsight';

interface SimulateResult {
  recommended_cluster?: string;
  recommended_hardware: string;
  recommended_quota: string;
  confidence: number;
  rationale: string;
  signals_used: string[];
  workload_profile?: { workload_type: string };
}

export default function Decisions() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [decisions, setDecisions] = useState<Record<string, OrchestrationDecision>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [simCatalog, setSimCatalog] = useState('');
  const [simResult, setSimResult] = useState<SimulateResult | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [catalogs, setCatalogs] = useState<string[]>([]);

  useEffect(() => {
    api.listSessions().then(s => {
      setSessions(s);
      s.forEach(sess => {
        api.getDecision(sess.request_id).then(d => {
          setDecisions(prev => ({ ...prev, [sess.session_id]: d }));
        }).catch(() => null);
      });
    }).catch(() => null);
    api.listCatalog().then(items => setCatalogs(items.map(i => i.catalog_item_id))).catch(() => null);
  }, []);

  const handleSimulate = async () => {
    if (!simCatalog) return;
    setSimulating(true);
    setSimResult(null);
    try {
      const res = await fetch('/api/intelligence/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ catalog_item_id: simCatalog, tenant_id: 'simulate' }),
      });
      if (res.ok) setSimResult(await res.json());
    } catch { /* ignore */ }
    setSimulating(false);
  };

  const recentSessions = sessions.slice(0, 10);

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Placement Decisions</h1>
        <p className="text-[#6A6E73] text-sm mt-1">
          Every provisioning request flows through the orchestration brain. It classifies the workload,
          selects optimal hardware, chooses the healthiest cluster, and records the outcome.
        </p>
      </div>

      {/* Simulate */}
      <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
        <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-3">Simulate a Decision</p>
        <p className="text-xs text-[#6A6E73] mb-3">See how the brain would classify a workload and select hardware without provisioning.</p>
        <div className="flex gap-3">
          <select
            value={simCatalog}
            onChange={e => setSimCatalog(e.target.value)}
            className="flex-1 bg-[#1a1a1a] border border-[#333] rounded px-3 py-2 text-sm text-white"
          >
            <option value="">Select a catalog item...</option>
            {catalogs.map(id => <option key={id} value={id}>{id}</option>)}
          </select>
          <button
            onClick={handleSimulate}
            disabled={!simCatalog || simulating}
            className="px-4 py-2 rounded text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40"
            style={{ backgroundColor: 'var(--brand-secondary)' }}
          >
            {simulating ? 'Deciding...' : 'Run Decision'}
          </button>
        </div>
        {simResult && (
          <div className="mt-4 grid md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-[#6A6E73]">Workload</p>
              <p className="text-sm text-white font-medium">{simResult.workload_profile?.workload_type?.replace(/_/g, ' ') || '—'}</p>
            </div>
            <div>
              <p className="text-xs text-[#6A6E73]">Hardware</p>
              <p className="text-sm text-white font-medium">{simResult.recommended_hardware}</p>
            </div>
            <div>
              <p className="text-xs text-[#6A6E73]">Cluster</p>
              <p className="text-sm text-white font-medium">{simResult.recommended_cluster || 'auto-select'}</p>
            </div>
            <div>
              <p className="text-xs text-[#6A6E73]">Confidence</p>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{
                    width: `${Math.round(simResult.confidence * 100)}%`,
                    backgroundColor: simResult.confidence >= 0.7 ? '#3E8635' : simResult.confidence >= 0.4 ? '#F0AB00' : '#C9190B',
                  }} />
                </div>
                <span className="text-xs font-mono text-[#6A6E73]">{Math.round(simResult.confidence * 100)}%</span>
              </div>
            </div>
            <div className="md:col-span-4 border-t border-[#333] pt-3">
              <p className="text-sm text-[#e0e0e0]">{simResult.rationale}</p>
              <div className="flex gap-1 mt-2">
                {simResult.signals_used.map(s => (
                  <span key={s} className="text-xs bg-[#1a1a1a] text-[#6A6E73] px-2 py-0.5 rounded">{s.replace(/_/g, ' ')}</span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Recent Sessions with Decisions */}
      <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Recent Sessions</p>
          <Link to="/catalog" className="text-xs text-[#0071C5] hover:underline">Provision New</Link>
        </div>
        {recentSessions.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-[#6A6E73] text-sm mb-2">No sessions yet</p>
            <p className="text-[#6A6E73] text-xs">Provision a workload to see the decision engine in action.</p>
          </div>
        ) : (
          <div className="space-y-1">
            {recentSessions.map(s => {
              const dec = decisions[s.session_id];
              const isExpanded = expandedId === s.session_id;
              return (
                <div key={s.session_id}>
                  <div
                    className="flex items-center justify-between py-2 px-2 rounded cursor-pointer hover:bg-white/5 transition"
                    onClick={() => setExpandedId(isExpanded ? null : s.session_id)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-mono text-[#6A6E73] w-16">{s.session_id.slice(0, 8)}</span>
                      <span className="text-sm text-white">{s.catalog_item_id}</span>
                      {dec?.workload_profile && (
                        <span className="text-xs bg-[#1a1a1a] text-[#6A6E73] px-2 py-0.5 rounded">
                          {dec.workload_profile.workload_type.replace(/_/g, ' ')}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      {dec && <span className="text-xs font-mono text-[#6A6E73]">{Math.round(dec.confidence * 100)}%</span>}
                      <StatusBadge status={s.status} />
                      <span className="text-[#6A6E73] text-xs">{isExpanded ? '▲' : '▼'}</span>
                    </div>
                  </div>
                  {isExpanded && (
                    <div className="px-2 pb-3">
                      {dec ? <DecisionInsight decision={dec} /> : (
                        <div className="bg-[#1a1a1a] rounded-lg p-4 text-sm text-[#6A6E73]">
                          No decision recorded. Enable ORCHESTRATION_BRAIN_ENABLED to capture placement decisions.
                          <Link to={`/sessions/${s.session_id}`} className="block mt-2 text-[#0071C5] hover:underline text-xs">View session details</Link>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
