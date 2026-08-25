import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

interface ClusterCapacity {
  cluster_name: string;
  score: number;
  health_status: string;
  cpu_utilization?: number;
  active_sandboxes: number;
}

interface FeedbackSummary {
  catalog_item_id: string;
  cluster_name: string;
  total_attempts: number;
  success_rate: number;
  recommendation: string;
}

export default function Overview() {
  const [clusters, setClusters] = useState<ClusterCapacity[]>([]);
  const [alerts, setAlerts] = useState<unknown[]>([]);
  const [feedback, setFeedback] = useState<FeedbackSummary[]>([]);
  const [catalogCount, setCatalogCount] = useState(0);
  const [sessionCount, setSessionCount] = useState(0);
  const [brainStatus, setBrainStatus] = useState<'connected' | 'degraded' | 'offline'>('offline');
  const [aiHealth, setAiHealth] = useState<{
    status?: string;
    models_available?: number;
    inference_canary?: string;
  } | null>(null);
  const [enrichment, setEnrichment] = useState<{
    summary?: { failure_classes?: number; top_failure?: string; open_incidents?: number; total_provisions?: number; provision_failure_rate?: number; pools_available?: number; active_signals?: number };
    failure_classes?: Record<string, number>;
    clusters?: Record<string, { total_pods?: number; pods_running?: number; pods_failed?: number; warning_events?: number; total_nodes?: number }>;
  } | null>(null);

  useEffect(() => {
    fetch('/api/intelligence/fleet-health', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { clusters: [], alerts: [] })
      .then(d => {
        setClusters(d.clusters || []);
        setAlerts(d.alerts || []);
        setBrainStatus(d.clusters?.length > 0 ? 'connected' : 'degraded');
      })
      .catch(() => setBrainStatus('offline'));

    fetch('/api/admin/feedback/summary', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { summaries: [] })
      .then(d => setFeedback(d.summaries || []))
      .catch(() => null);

    api.listCatalog().then(items => setCatalogCount(items.length)).catch(() => null);

    fetch('/api/intelligence/enrichment', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : null)
      .then(setEnrichment)
      .catch(() => null);
    api.listSessions().then(s => setSessionCount(s.length)).catch(() => null);
    fetch('/api/admin/system/health', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : null)
      .then(d => setAiHealth(d?.checks?.litellm || null))
      .catch(() => setAiHealth(null));
  }, []);

  const healthyClusters = clusters.filter(c => c.health_status === 'healthy').length;
  const totalSandboxes = clusters.reduce((s, c) => s + c.active_sandboxes, 0);
  const totalOutcomes = feedback.reduce((s, f) => s + f.total_attempts, 0);
  const avoidCount = feedback.filter(f => f.recommendation === 'avoid').length;
  const statusColor = brainStatus === 'connected' ? '#3E8635' : brainStatus === 'degraded' ? '#F0AB00' : '#C9190B';

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>
            Intelligence Overview
          </h1>
          <p className="text-[#6A6E73] text-sm mt-1">
            Launchpad decides where, how, and when to provision AI workloads across the fleet.
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg" style={{ backgroundColor: `${statusColor}20` }}>
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
          <span className="text-xs font-medium" style={{ color: statusColor }}>
            {brainStatus === 'connected' ? 'Brain Connected' : brainStatus === 'degraded' ? 'Degraded' : 'Offline'}
          </span>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {[
          { label: 'Fleet Clusters', value: clusters.length > 0 ? `${healthyClusters}/${clusters.length}` : '—', sub: 'healthy', color: '#0071C5', link: '/fleet' },
          { label: 'Active Sandboxes', value: totalSandboxes || '—', sub: 'across fleet', color: '#0071C5', link: '/fleet' },
          { label: 'Catalog Items', value: catalogCount || '—', sub: `${sessionCount} sessions`, color: '#3E8635', link: '/workloads' },
          { label: 'Outcomes Tracked', value: totalOutcomes || '—', sub: 'decisions recorded', color: totalOutcomes > 0 ? '#3E8635' : '#6A6E73', link: '/feedback' },
          { label: 'Avoid-Listed', value: avoidCount, sub: 'failing combos', color: avoidCount > 0 ? '#C9190B' : '#3E8635', link: '/feedback' },
          {
            label: 'AI Gateway',
            value: aiHealth?.status === 'pass' ? 'Healthy' : aiHealth ? 'Degraded' : '—',
            sub: aiHealth?.models_available != null
              ? `${aiHealth.models_available} models${aiHealth.inference_canary === 'pass' ? ' · canary passed' : ''}`
              : 'awaiting authenticated check',
            color: aiHealth?.status === 'pass' ? '#3E8635' : aiHealth ? '#C9190B' : '#6A6E73',
            link: '/admin',
          },
        ].map(card => (
          <Link key={card.label} to={card.link} className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4 hover:border-[#555] transition">
            <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">{card.label}</p>
            <p className="text-2xl font-bold mt-1" style={{ color: card.color }}>{card.value}</p>
            <p className="text-xs text-[#6A6E73] mt-1">{card.sub}</p>
          </Link>
        ))}
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <Link to="/fleet" className="block bg-[#212121] border border-[#C9190B]/30 rounded-lg p-4 hover:border-[#C9190B]/50 transition">
          <p className="text-xs text-[#C9190B] uppercase tracking-wider font-bold">{alerts.length} Health Alert{alerts.length !== 1 ? 's' : ''}</p>
          <p className="text-sm text-[#6A6E73] mt-1">View fleet health for details</p>
        </Link>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Fleet summary */}
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Fleet at a Glance</p>
            <Link to="/fleet" className="text-xs text-[#0071C5] hover:underline">View fleet</Link>
          </div>
          {clusters.length === 0 ? (
            <p className="text-sm text-[#6A6E73] py-6 text-center">Connecting to StarGate...</p>
          ) : (
            <div className="space-y-2">
              {clusters.map(c => (
                <div key={c.cluster_name} className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{
                    backgroundColor: c.health_status === 'healthy' ? '#3E8635' : c.health_status === 'warning' ? '#F0AB00' : '#C9190B'
                  }} />
                  <span className="text-sm text-white w-28 truncate">{c.cluster_name}</span>
                  <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{
                      width: `${Math.min(100, c.score)}%`,
                      backgroundColor: c.health_status === 'healthy' ? '#0071C5' : '#F0AB00',
                    }} />
                  </div>
                  <span className="text-xs font-mono text-[#6A6E73] w-8 text-right">{Math.round(c.score)}</span>
                  <span className="text-xs text-[#6A6E73] w-12 text-right">{c.active_sandboxes} sb</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Intelligence pipeline */}
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Intelligence Pipeline</p>
          <div className="space-y-3">
            {[
              { name: 'Workload Classifier', desc: `${catalogCount} items classified by type, intensity, GPU needs`, status: 'active', link: '/workloads' },
              { name: 'Placement Service', desc: `${clusters.length} clusters scored, capacity cached every 60s`, status: clusters.length > 0 ? 'active' : 'waiting', link: '/fleet' },
              { name: 'Feedback Tracker', desc: `${totalOutcomes} outcomes recorded, ${avoidCount} combos avoided`, status: totalOutcomes > 0 ? 'active' : 'waiting', link: '/feedback' },
              { name: 'Orchestration Brain', desc: 'Composes all signals into placement decisions', status: brainStatus === 'connected' ? 'active' : 'waiting', link: '/decisions' },
            ].map(svc => (
              <Link key={svc.name} to={svc.link} className="flex items-center gap-3 p-3 rounded-lg hover:bg-white/5 transition">
                <span className="w-2 h-2 rounded-full shrink-0" style={{
                  backgroundColor: svc.status === 'active' ? '#3E8635' : '#F0AB00'
                }} />
                <div className="flex-1">
                  <p className="text-sm text-white font-medium">{svc.name}</p>
                  <p className="text-xs text-[#6A6E73]">{svc.desc}</p>
                </div>
                <span className="text-xs text-[#6A6E73]">→</span>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Enrichment insights */}
      {enrichment?.summary && (enrichment.summary.total_provisions || 0) > 0 && (
        <div className="grid md:grid-cols-3 gap-6">
          {/* Provisioning health */}
          <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
            <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-3">Provisioning Health</p>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-[#6A6E73]">Total provisions</span>
                <span className="text-white font-medium">{enrichment.summary.total_provisions?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-[#6A6E73]">Failure rate</span>
                <span style={{ color: (enrichment.summary.provision_failure_rate || 0) < 2 ? '#3E8635' : '#F0AB00' }} className="font-medium">
                  {enrichment.summary.provision_failure_rate}%
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-[#6A6E73]">Pools available</span>
                <span className="text-white">{enrichment.summary.pools_available}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-[#6A6E73]">Open incidents</span>
                <span style={{ color: (enrichment.summary.open_incidents || 0) > 0 ? '#F0AB00' : '#3E8635' }}>
                  {enrichment.summary.open_incidents}
                </span>
              </div>
            </div>
          </div>

          {/* Top failure classes */}
          <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
            <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-3">Top Failure Classes</p>
            {enrichment.failure_classes && Object.keys(enrichment.failure_classes).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(enrichment.failure_classes)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 5)
                  .map(([name, count]) => (
                    <div key={name} className="flex items-center gap-2 text-xs">
                      <span className="text-[#e0e0e0] flex-1 truncate">{name.replace(/_/g, ' ')}</span>
                      <div className="w-16 h-1 bg-[#333] rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-[#C9190B]" style={{
                          width: `${Math.min(100, (count / (Object.values(enrichment.failure_classes!)[0] || 1)) * 100)}%`
                        }} />
                      </div>
                      <span className="text-[#6A6E73] font-mono w-12 text-right">{count.toLocaleString()}</span>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="text-sm text-[#6A6E73]">No failure data</p>
            )}
          </div>

          {/* Cluster pod health */}
          <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
            <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-3">Fleet Pod Health</p>
            {enrichment.clusters && Object.keys(enrichment.clusters).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(enrichment.clusters).slice(0, 6).map(([name, info]) => {
                  const total = info.total_pods || 0;
                  const running = info.pods_running || 0;
                  const pct = total > 0 ? Math.round((running / total) * 100) : 0;
                  return (
                    <div key={name} className="flex items-center gap-2 text-xs">
                      <span className="text-[#e0e0e0] w-20 truncate">{name}</span>
                      <div className="flex-1 h-1 bg-[#333] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: pct >= 80 ? '#3E8635' : '#F0AB00' }} />
                      </div>
                      <span className="text-[#6A6E73] font-mono w-16 text-right">{running}/{total}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-[#6A6E73]">Waiting for DeepField...</p>
            )}
          </div>
        </div>
      )}

      {/* Quick actions */}
      <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
        <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-3">Quick Actions</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Link to="/decisions" className="flex items-center gap-2 px-4 py-3 rounded-lg border border-[#333] text-white hover:border-[#555] transition text-sm">
            <span className="text-[#0071C5]">◆</span> Simulate Decision
          </Link>
          <Link to="/workloads" className="flex items-center gap-2 px-4 py-3 rounded-lg border border-[#333] text-white hover:border-[#555] transition text-sm">
            <span className="text-[#3E8635]">◆</span> View Workloads
          </Link>
          <Link to="/fleet" className="flex items-center gap-2 px-4 py-3 rounded-lg border border-[#333] text-white hover:border-[#555] transition text-sm">
            <span className="text-[#0071C5]">◆</span> Fleet Health
          </Link>
          <Link to="/catalog" className="flex items-center gap-2 px-4 py-3 rounded-lg border border-[#333] text-white hover:border-[#555] transition text-sm">
            <span className="text-[#F0AB00]">◆</span> Browse Catalog
          </Link>
        </div>
      </div>
    </div>
  );
}
