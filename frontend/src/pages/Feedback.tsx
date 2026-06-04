import React, { useEffect, useState } from 'react';
import StatusBadge from '../components/StatusBadge';

interface FeedbackSummary {
  catalog_item_id: string;
  cluster_name: string;
  hardware_profile: string;
  total_attempts: number;
  success_count: number;
  success_rate: number;
  avg_latency_ms: number;
  last_failure_reason?: string;
  confidence: number;
  recommendation: string;
}

interface ProvisioningOutcome {
  outcome_id: string;
  session_id: string;
  catalog_item_id: string;
  cluster_name?: string;
  hardware_profile: string;
  workload_type?: string;
  success: boolean;
  failure_reason?: string;
  provision_latency_ms: number;
  validation_passed: boolean;
  created_at: string;
}

type TabKey = 'cluster' | 'catalog' | 'hardware' | 'workload';

function groupBy<T>(items: T[], key: (item: T) => string): Record<string, T[]> {
  return items.reduce<Record<string, T[]>>((acc, item) => {
    const k = key(item);
    (acc[k] = acc[k] || []).push(item);
    return acc;
  }, {});
}

export default function Feedback() {
  const [summaries, setSummaries] = useState<FeedbackSummary[]>([]);
  const [tab, setTab] = useState<TabKey>('cluster');
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<ProvisioningOutcome[]>([]);

  useEffect(() => {
    fetch('/api/admin/feedback/summary', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { summaries: [] })
      .then(d => { setSummaries(d.summaries || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const loadOutcomes = (catalogItemId?: string, clusterName?: string) => {
    const params = new URLSearchParams();
    if (catalogItemId) params.set('catalog_item_id', catalogItemId);
    if (clusterName) params.set('cluster_name', clusterName);
    fetch(`/api/admin/feedback/outcomes?${params}`, { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { outcomes: [] })
      .then(d => setOutcomes(d.outcomes || []))
      .catch(() => setOutcomes([]));
  };

  const totalAttempts = summaries.reduce((s, f) => s + f.total_attempts, 0);
  const totalSuccess = summaries.reduce((s, f) => s + f.success_count, 0);
  const overallRate = totalAttempts > 0 ? Math.round((totalSuccess / totalAttempts) * 100) : 0;
  const avoidList = summaries.filter(s => s.recommendation === 'avoid');

  const grouped = tab === 'cluster'
    ? groupBy(summaries, s => s.cluster_name)
    : tab === 'catalog'
      ? groupBy(summaries, s => s.catalog_item_id)
      : tab === 'workload'
        ? groupBy(summaries, s => (s as FeedbackSummary & { workload_type?: string }).workload_type || 'unknown')
        : groupBy(summaries, s => s.hardware_profile);

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Feedback Loops</h1>
        <p className="text-[#6A6E73] text-sm mt-1">
          Every provisioning outcome is recorded. Success rates, latency, and failure reasons
          feed back into the decision engine — clusters with poor track records are automatically avoided.
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Total Outcomes</p>
          <p className="text-2xl font-bold text-white mt-1">{totalAttempts}</p>
        </div>
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Success Rate</p>
          <p className="text-2xl font-bold mt-1" style={{ color: overallRate >= 80 ? '#3E8635' : overallRate >= 30 ? '#F0AB00' : '#C9190B' }}>
            {totalAttempts > 0 ? `${overallRate}%` : '—'}
          </p>
        </div>
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Avoid-Listed</p>
          <p className="text-2xl font-bold mt-1" style={{ color: avoidList.length > 0 ? '#C9190B' : '#3E8635' }}>
            {avoidList.length}
          </p>
          <p className="text-xs text-[#6A6E73] mt-1">&lt;30% success, 5+ attempts</p>
        </div>
      </div>

      {/* Avoid List */}
      {avoidList.length > 0 && (
        <div className="bg-[#212121] border border-[#C9190B]/30 rounded-lg p-4">
          <p className="text-xs text-[#C9190B] uppercase tracking-wider font-bold mb-3">Avoid List</p>
          <p className="text-xs text-[#6A6E73] mb-3">These cluster/catalog/hardware combinations have failed too often. The decision engine will not place workloads here.</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase border-b border-[#333]">
                <th className="pb-2 pr-4">Cluster</th>
                <th className="pb-2 pr-4">Catalog Item</th>
                <th className="pb-2 pr-4">Hardware</th>
                <th className="pb-2 pr-4">Rate</th>
                <th className="pb-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {avoidList.map(s => (
                <tr key={`${s.cluster_name}-${s.catalog_item_id}-${s.hardware_profile}`} className="border-b border-[#1a1a1a] last:border-0">
                  <td className="py-2 pr-4 text-white">{s.cluster_name}</td>
                  <td className="py-2 pr-4 text-white font-mono text-xs">{s.catalog_item_id}</td>
                  <td className="py-2 pr-4 text-white">{s.hardware_profile}</td>
                  <td className="py-2 pr-4 text-[#C9190B] font-medium">{Math.round(s.success_rate * 100)}%</td>
                  <td className="py-2 text-[#6A6E73] text-xs">{s.last_failure_reason || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab filters */}
      <div className="flex gap-2">
        {([
          { key: 'cluster' as TabKey, label: 'By Cluster' },
          { key: 'catalog' as TabKey, label: 'By Catalog Item' },
          { key: 'hardware' as TabKey, label: 'By Hardware' },
          { key: 'workload' as TabKey, label: 'By Workload Type' },
        ]).map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 rounded text-xs font-medium transition ${
              tab === t.key ? 'bg-white/15 text-white' : 'text-[#6A6E73] hover:text-white hover:bg-white/10'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Data table */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-12 bg-[#212121] rounded-lg animate-pulse" />)}
        </div>
      ) : summaries.length === 0 ? (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-12 text-center">
          <p className="text-[#6A6E73] text-sm mb-2">No feedback data yet</p>
          <p className="text-[#6A6E73] text-xs">Enable FEEDBACK_TRACKING_ENABLED and provision some workloads to start collecting outcomes.</p>
        </div>
      ) : (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase border-b border-[#333]">
                <th className="pb-2 pr-4">{tab === 'cluster' ? 'Cluster' : tab === 'catalog' ? 'Catalog Item' : tab === 'workload' ? 'Workload Type' : 'Hardware'}</th>
                <th className="pb-2 pr-4">Attempts</th>
                <th className="pb-2 pr-4">Success Rate</th>
                <th className="pb-2 pr-4">Avg Latency</th>
                <th className="pb-2 pr-4">Confidence</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([key, items]) => {
                const total = items.reduce((s, i) => s + i.total_attempts, 0);
                const success = items.reduce((s, i) => s + i.success_count, 0);
                const rate = total > 0 ? success / total : 0;
                const pct = Math.round(rate * 100);
                const latency = items.reduce((s, i) => s + i.avg_latency_ms, 0) / items.length;
                const worst = items.some(i => i.recommendation === 'avoid') ? 'avoid' : items.some(i => i.recommendation === 'preferred') ? 'preferred' : 'acceptable';
                const avgConfidence = items.reduce((s, i) => s + i.confidence, 0) / items.length;
                const isExpanded = expandedRow === key;
                return (
                  <React.Fragment key={key}>
                    <tr
                      className="border-b border-[#1a1a1a] last:border-0 cursor-pointer hover:bg-white/5 transition"
                      onClick={() => {
                        if (isExpanded) { setExpandedRow(null); setOutcomes([]); }
                        else {
                          setExpandedRow(key);
                          const params: Record<string, string> = {};
                          if (tab === 'cluster') params.cluster_name = key;
                          else if (tab === 'catalog') params.catalog_item_id = key;
                          loadOutcomes(params.catalog_item_id, params.cluster_name);
                        }
                      }}
                    >
                      <td className="py-2 pr-4 text-white font-medium">{key}</td>
                      <td className="py-2 pr-4 text-[#e0e0e0]">{total}</td>
                      <td className="py-2 pr-4">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-[#333] rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: pct >= 80 ? '#3E8635' : pct >= 30 ? '#F0AB00' : '#C9190B' }} />
                          </div>
                          <span className="text-xs font-mono" style={{ color: pct >= 80 ? '#3E8635' : pct >= 30 ? '#F0AB00' : '#C9190B' }}>{pct}%</span>
                        </div>
                      </td>
                      <td className="py-2 pr-4 text-[#6A6E73] font-mono text-xs">{Math.round(latency)}ms</td>
                      <td className="py-2 pr-4 text-[#6A6E73] font-mono text-xs">{Math.round(avgConfidence * 100)}%</td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={worst} />
                          <span className="text-[#6A6E73] text-xs">{isExpanded ? '▲' : '▼'}</span>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={6} className="py-3 px-2">
                          {outcomes.length === 0 ? (
                            <p className="text-[#6A6E73] text-xs text-center py-4">No individual outcomes recorded</p>
                          ) : (
                            <div className="bg-[#1a1a1a] rounded-lg p-3">
                              <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-2">Individual Outcomes ({outcomes.length})</p>
                              <div className="space-y-1">
                                {outcomes.slice(0, 10).map(o => (
                                  <div key={o.outcome_id} className="flex items-center gap-3 text-xs py-1 border-b border-[#212121] last:border-0">
                                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: o.success ? '#3E8635' : '#C9190B' }} />
                                    <span className="font-mono text-[#6A6E73] w-16">{o.session_id.slice(0, 8)}</span>
                                    <span className="text-white w-32 truncate">{o.catalog_item_id}</span>
                                    <span className="text-[#6A6E73]">{o.hardware_profile}</span>
                                    <span className="text-[#6A6E73] font-mono">{o.provision_latency_ms}ms</span>
                                    <span className={o.validation_passed ? 'text-[#3E8635]' : 'text-[#C9190B]'}>
                                      {o.validation_passed ? 'validated' : 'failed'}
                                    </span>
                                    {o.failure_reason && <span className="text-[#C9190B] truncate flex-1">{o.failure_reason}</span>}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
