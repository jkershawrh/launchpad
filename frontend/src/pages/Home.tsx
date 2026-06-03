import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import StatusBadge from '../components/StatusBadge';

interface ClusterCapacity {
  cluster_name: string;
  score: number;
  health_status: string;
  cpu_utilization?: number;
  gpu_available?: boolean;
}

interface HealthAlert {
  alert_id: string;
  cluster_name: string;
  severity: string;
  recommended_action: string;
}

interface FeedbackSummary {
  catalog_item_id: string;
  cluster_name: string;
  hardware_profile: string;
  total_attempts: number;
  success_rate: number;
  avg_latency_ms: number;
  recommendation: string;
}

export default function Home() {
  const [clusters, setClusters] = useState<ClusterCapacity[]>([]);
  const [alerts, setAlerts] = useState<HealthAlert[]>([]);
  const [feedback, setFeedback] = useState<FeedbackSummary[]>([]);
  const [sessionCount, setSessionCount] = useState({ active: 0, total: 0 });

  useEffect(() => {
    fetch('/api/intelligence/fleet-health', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { clusters: [], alerts: [] })
      .then(d => { setClusters(d.clusters || []); setAlerts(d.alerts || []); })
      .catch(() => null);
    fetch('/api/admin/feedback/summary', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { summaries: [] })
      .then(d => setFeedback(d.summaries || []))
      .catch(() => null);
    api.listSessions().then(s => {
      const active = s.filter(x => ['ready', 'active', 'provisioning', 'validating'].includes(x.status)).length;
      setSessionCount({ active, total: s.length });
    }).catch(() => null);
  }, []);

  const healthyClusters = clusters.filter(c => c.health_status === 'healthy').length;
  const totalAttempts = feedback.reduce((s, f) => s + f.total_attempts, 0);
  const totalSuccess = feedback.reduce((s, f) => s + (f.success_rate * f.total_attempts), 0);
  const overallRate = totalAttempts > 0 ? Math.round((totalSuccess / totalAttempts) * 100) : 0;
  const avoidCount = feedback.filter(f => f.recommendation === 'avoid').length;

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Active Sessions', value: sessionCount.active, sub: `${sessionCount.total} total`, color: '#3E8635' },
          { label: 'Fleet Clusters', value: clusters.length > 0 ? `${healthyClusters}/${clusters.length}` : '—', sub: 'healthy / total', color: '#0071C5' },
          { label: 'Success Rate', value: totalAttempts > 0 ? `${overallRate}%` : '—', sub: `${totalAttempts} decisions`, color: overallRate >= 80 ? '#3E8635' : '#F0AB00' },
          { label: 'Avoid-Listed', value: avoidCount, sub: 'failing combos', color: avoidCount > 0 ? '#C9190B' : '#3E8635' },
        ].map(card => (
          <div key={card.label} className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
            <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">{card.label}</p>
            <p className="text-2xl font-bold mt-1" style={{ color: card.color }}>{card.value}</p>
            <p className="text-xs text-[#6A6E73] mt-1">{card.sub}</p>
          </div>
        ))}
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="bg-[#212121] border border-[#C9190B]/30 rounded-lg p-4">
          <p className="text-xs text-[#C9190B] uppercase tracking-wider font-bold mb-3">Health Alerts</p>
          <div className="space-y-2">
            {alerts.map(a => (
              <div key={a.alert_id} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <StatusBadge status={a.severity} />
                  <span className="text-white">{a.cluster_name}</span>
                </div>
                <span className="text-[#6A6E73] text-xs">{a.recommended_action}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Fleet Health */}
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Fleet Health</p>
          {clusters.length === 0 ? (
            <div className="text-sm text-[#6A6E73] py-8 text-center">
              No cluster data available
            </div>
          ) : (
            <div className="space-y-3">
              {clusters.map(c => (
                <div key={c.cluster_name} className="flex items-center gap-3">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: c.health_status === 'healthy' ? '#3E8635' : c.health_status === 'degraded' ? '#F0AB00' : '#C9190B' }}
                  />
                  <span className="text-sm text-white w-36 truncate">{c.cluster_name}</span>
                  <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.min(100, c.score)}%`,
                        backgroundColor: c.health_status === 'healthy' ? '#0071C5' : '#C9190B',
                      }}
                    />
                  </div>
                  <span className="text-xs font-mono text-[#6A6E73] w-8 text-right">{Math.round(c.score)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quick Launch */}
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Get Started</p>
          <div className="space-y-3">
            <Link to="/demos" className="flex items-center gap-3 px-4 py-3 rounded-lg text-white transition hover:opacity-90" style={{ backgroundColor: 'var(--brand-primary)' }}>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <div>
                <div className="font-medium text-sm">Launch a Demo</div>
                <div className="text-xs opacity-70">10 custom demos + 7 AI quickstarts</div>
              </div>
            </Link>
            <Link to="/sandbox" className="flex items-center gap-3 px-4 py-3 rounded-lg border border-[#333] text-white hover:border-[#555] transition">
              <svg className="w-5 h-5 text-[#0071C5]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
              <div>
                <div className="font-medium text-sm">Open a Sandbox</div>
                <div className="text-xs text-[#6A6E73]">Configurable environments with full hardware access</div>
              </div>
            </Link>
            <Link to="/catalog" className="flex items-center gap-3 px-4 py-3 rounded-lg border border-[#333] text-white hover:border-[#555] transition">
              <svg className="w-5 h-5 text-[#3E8635]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
              <div>
                <div className="font-medium text-sm">Browse Catalog</div>
                <div className="text-xs text-[#6A6E73]">25 catalog items across 3 categories</div>
              </div>
            </Link>
          </div>
        </div>
      </div>

      {/* Provisioning History */}
      {feedback.length > 0 && (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Provisioning History</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase border-b border-[#333]">
                <th className="pb-2 pr-4">Catalog Item</th>
                <th className="pb-2 pr-4">Cluster</th>
                <th className="pb-2 pr-4">Hardware</th>
                <th className="pb-2 pr-4">Success</th>
                <th className="pb-2 pr-4">Latency</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {feedback.slice(0, 8).map(f => {
                const pct = Math.round(f.success_rate * 100);
                return (
                  <tr key={`${f.cluster_name}-${f.catalog_item_id}-${f.hardware_profile}`} className="border-b border-[#1a1a1a] last:border-0">
                    <td className="py-2 pr-4 text-white text-xs font-mono">{f.catalog_item_id}</td>
                    <td className="py-2 pr-4 text-[#e0e0e0]">{f.cluster_name}</td>
                    <td className="py-2 pr-4 text-[#e0e0e0]">{f.hardware_profile}</td>
                    <td className="py-2 pr-4">
                      <span style={{ color: pct >= 80 ? '#3E8635' : pct >= 30 ? '#F0AB00' : '#C9190B' }} className="font-medium">
                        {pct}%
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-[#6A6E73] font-mono text-xs">{Math.round(f.avg_latency_ms)}ms</td>
                    <td className="py-2"><StatusBadge status={f.recommendation} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pipeline */}
      <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
        <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-3">Intelligence Pipeline</p>
        <div className="flex justify-center gap-2 text-xs overflow-x-auto py-2">
          {[
            { step: 'Request', color: '#6A6E73' },
            { step: 'Classify', color: '#0071C5' },
            { step: 'Place', color: '#0071C5' },
            { step: 'Provision', color: '#3E8635' },
            { step: 'Validate', color: '#3E8635' },
            { step: 'Learn', color: '#F0AB00' },
            { step: 'Ready', color: '#3E8635' },
          ].map((s, i) => (
            <div key={s.step} className="flex items-center gap-2 shrink-0">
              <span className="px-3 py-1.5 rounded font-medium text-white" style={{ backgroundColor: s.color }}>
                {s.step}
              </span>
              {i < 6 && <span className="text-[#333]">{"→"}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
