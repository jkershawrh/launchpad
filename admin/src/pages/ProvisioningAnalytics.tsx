import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ClusterCapacity, FeedbackSummary, HealthAlert } from '../api/types';
import StatusBadge from '../components/StatusBadge';

type TabKey = 'cluster' | 'catalog' | 'hardware';

function RecommendationBadge({ recommendation }: { recommendation: string }) {
  const colors: Record<string, string> = {
    preferred: 'bg-[#3E8635] text-white',
    acceptable: 'bg-[#F0AB00] text-[#151515]',
    avoid: 'bg-[#C9190B] text-white',
  };
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded ${colors[recommendation] || 'bg-gray-200 text-gray-700'}`}>
      {recommendation}
    </span>
  );
}

function SuccessRateCell({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  const color = pct >= 80 ? 'text-[#3E8635]' : pct >= 30 ? 'text-[#F0AB00]' : 'text-[#C9190B]';
  return <span className={`font-medium ${color}`}>{pct}%</span>;
}

function groupBy<T>(items: T[], key: (item: T) => string): Record<string, T[]> {
  return items.reduce<Record<string, T[]>>((acc, item) => {
    const k = key(item);
    (acc[k] = acc[k] || []).push(item);
    return acc;
  }, {});
}

export default function ProvisioningAnalytics() {
  const [summaries, setSummaries] = useState<FeedbackSummary[]>([]);
  const [clusters, setClusters] = useState<ClusterCapacity[]>([]);
  const [alerts, setAlerts] = useState<HealthAlert[]>([]);
  const [tab, setTab] = useState<TabKey>('cluster');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getFeedbackSummary().catch(() => ({ summaries: [] })),
      api.getFleetHealth().catch(() => ({ clusters: [], alerts: [] })),
    ]).then(([fb, fh]) => {
      setSummaries(fb.summaries);
      setClusters(fh.clusters);
      setAlerts(fh.alerts);
      setLoading(false);
    });
  }, []);

  const totalAttempts = summaries.reduce((sum, s) => sum + s.total_attempts, 0);
  const totalSuccess = summaries.reduce((sum, s) => sum + s.success_count, 0);
  const overallRate = totalAttempts > 0 ? totalSuccess / totalAttempts : 0;
  const avgLatency = summaries.length > 0
    ? summaries.reduce((sum, s) => sum + s.avg_latency_ms, 0) / summaries.length
    : 0;
  const avoidList = summaries.filter((s) => s.recommendation === 'avoid');

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;

  const grouped = tab === 'cluster'
    ? groupBy(summaries, (s) => s.cluster_name)
    : tab === 'catalog'
      ? groupBy(summaries, (s) => s.catalog_item_id)
      : groupBy(summaries, (s) => s.hardware_profile);

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">Provisioning Analytics</h1>
      <p className="text-[#6A6E73] mb-8">Intelligence layer performance and feedback history.</p>

      {/* Summary cards */}
      <div className="grid sm:grid-cols-5 gap-4 mb-8">
        {[
          { label: 'Total Decisions', value: totalAttempts, color: 'text-[#151515]' },
          { label: 'Success Rate', value: `${Math.round(overallRate * 100)}%`, color: overallRate >= 0.8 ? 'text-[#3E8635]' : 'text-[#F0AB00]' },
          { label: 'Avg Latency', value: `${Math.round(avgLatency)}ms`, color: 'text-[#151515]' },
          { label: 'Avoid-Listed', value: avoidList.length, color: avoidList.length > 0 ? 'text-[#C9190B]' : 'text-[#3E8635]' },
          { label: 'Active Clusters', value: clusters.length, color: 'text-[#0068B5]' },
        ].map((card) => (
          <div key={card.label} className="bg-white rounded border border-[#D2D2D2] p-5">
            <p className="text-xs text-[#6A6E73] uppercase font-medium">{card.label}</p>
            <p className={`text-3xl font-bold mt-1 ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      {/* Health alerts */}
      {alerts.length > 0 && (
        <div className="bg-white rounded border border-[#D2D2D2] border-l-4 border-l-[#C9190B] p-6 mb-8">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Health Alerts</h2>
          <div className="space-y-2">
            {alerts.map((a) => (
              <div key={a.alert_id} className="flex items-center justify-between text-sm py-2 border-b border-[#F0F0F0] last:border-0">
                <div className="flex items-center gap-2">
                  <StatusBadge status={a.severity} />
                  <span className="text-[#151515]">{a.cluster_name}</span>
                </div>
                <span className="text-[#6A6E73] text-xs">{a.recommended_action}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab navigation */}
      <div className="flex gap-2 mb-6">
        {([
          { key: 'cluster' as TabKey, label: 'By Cluster' },
          { key: 'catalog' as TabKey, label: 'By Catalog Item' },
          { key: 'hardware' as TabKey, label: 'By Hardware' },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              tab === t.key
                ? 'bg-[#151515] text-white'
                : 'bg-white border border-[#D2D2D2] text-[#6A6E73] hover:bg-[#F0F0F0]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Data table */}
      {summaries.length === 0 ? (
        <div className="bg-white rounded border border-[#D2D2D2] p-12 text-center">
          <p className="text-[#6A6E73]">No feedback data yet. Provision some sessions to start collecting analytics.</p>
        </div>
      ) : (
        <div className="bg-white rounded border border-[#D2D2D2] p-6 mb-8">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase border-b border-[#D2D2D2]">
                <th className="pb-2 pr-4">{tab === 'cluster' ? 'Cluster' : tab === 'catalog' ? 'Catalog Item' : 'Hardware'}</th>
                <th className="pb-2 pr-4">Attempts</th>
                <th className="pb-2 pr-4">Success Rate</th>
                <th className="pb-2 pr-4">Avg Latency</th>
                <th className="pb-2 pr-4">Recommendation</th>
                <th className="pb-2">Last Failure</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([key, items]) => {
                const total = items.reduce((s, i) => s + i.total_attempts, 0);
                const success = items.reduce((s, i) => s + i.success_count, 0);
                const rate = total > 0 ? success / total : 0;
                const latency = items.reduce((s, i) => s + i.avg_latency_ms, 0) / items.length;
                const worst = items.reduce<string | undefined>((w, i) => i.recommendation === 'avoid' ? 'avoid' : w || i.recommendation, undefined) || 'acceptable';
                const lastFail = items.find((i) => i.last_failure_reason)?.last_failure_reason;
                return (
                  <tr key={key} className="border-b border-[#F0F0F0] last:border-0">
                    <td className="py-3 pr-4 text-[#151515] font-medium">{key}</td>
                    <td className="py-3 pr-4 text-[#151515]">{total}</td>
                    <td className="py-3 pr-4"><SuccessRateCell rate={rate} /></td>
                    <td className="py-3 pr-4 text-[#151515] font-mono text-xs">{Math.round(latency)}ms</td>
                    <td className="py-3 pr-4"><RecommendationBadge recommendation={worst} /></td>
                    <td className="py-3 text-[#6A6E73] text-xs truncate max-w-[200px]">{lastFail || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Avoid list */}
      {avoidList.length > 0 && (
        <div className="bg-white rounded border border-[#D2D2D2] border-l-4 border-l-[#C9190B] p-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Avoid List</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase border-b border-[#D2D2D2]">
                <th className="pb-2 pr-4">Cluster</th>
                <th className="pb-2 pr-4">Catalog Item</th>
                <th className="pb-2 pr-4">Hardware</th>
                <th className="pb-2 pr-4">Success Rate</th>
                <th className="pb-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {avoidList.map((s) => (
                <tr key={`${s.cluster_name}-${s.catalog_item_id}-${s.hardware_profile}`} className="border-b border-[#F0F0F0] last:border-0">
                  <td className="py-3 pr-4 text-[#151515]">{s.cluster_name}</td>
                  <td className="py-3 pr-4 text-[#151515]">{s.catalog_item_id}</td>
                  <td className="py-3 pr-4 text-[#151515]">{s.hardware_profile}</td>
                  <td className="py-3 pr-4"><SuccessRateCell rate={s.success_rate} /></td>
                  <td className="py-3 text-[#6A6E73] text-xs">{s.last_failure_reason || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
