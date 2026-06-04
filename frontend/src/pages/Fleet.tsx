import { useEffect, useState } from 'react';
import StatusBadge from '../components/StatusBadge';

interface ClusterCapacity {
  cluster_name: string;
  score: number;
  health_status: string;
  cpu_utilization?: number;
  gpu_available?: boolean;
  active_sandboxes: number;
  vm_density?: number;
  hot_nodes: number;
  health_rate?: number;
  last_updated: string;
}

interface HealthAlert {
  alert_id: string;
  cluster_name: string;
  alert_type: string;
  severity: string;
  recommended_action: string;
  created_at: string;
}

interface DeepFieldSignal {
  metric_type: string;
  value: number;
  threshold: number;
  status: string;
}

export default function Fleet() {
  const [clusters, setClusters] = useState<ClusterCapacity[]>([]);
  const [alerts, setAlerts] = useState<HealthAlert[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);
  const [signals, setSignals] = useState<DeepFieldSignal[]>([]);

  useEffect(() => {
    const poll = () => {
      fetch('/api/intelligence/fleet-health', { credentials: 'same-origin' })
        .then(r => r.ok ? r.json() : { clusters: [], alerts: [] })
        .then(d => { setClusters(d.clusters || []); setAlerts(d.alerts || []); })
        .catch(() => null);
    };
    poll();
    const interval = setInterval(poll, 15000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!selectedCluster) { setSignals([]); return; }
    fetch(`/api/intelligence/cluster/${selectedCluster}/signals`, { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : { signals: [] })
      .then(d => setSignals(d.signals || []))
      .catch(() => setSignals([]));
  }, [selectedCluster]);

  const healthyCt = clusters.filter(c => c.health_status === 'healthy').length;

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Red Hat Display' }}>Fleet Health</h1>
        <p className="text-[#6A6E73] text-sm mt-1">
          Real-time cluster capacity from StarGate and health signals from DeepField.
          The placement engine uses this data to select the best cluster for each workload.
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Clusters</p>
          <p className="text-2xl font-bold text-white mt-1">{clusters.length > 0 ? `${healthyCt}/${clusters.length}` : '—'}</p>
          <p className="text-xs text-[#6A6E73] mt-1">healthy / total</p>
        </div>
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Active Sandboxes</p>
          <p className="text-2xl font-bold text-[#0071C5] mt-1">{clusters.reduce((s, c) => s + c.active_sandboxes, 0) || '—'}</p>
          <p className="text-xs text-[#6A6E73] mt-1">across fleet</p>
        </div>
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Alerts</p>
          <p className="text-2xl font-bold mt-1" style={{ color: alerts.length > 0 ? '#C9190B' : '#3E8635' }}>{alerts.length}</p>
          <p className="text-xs text-[#6A6E73] mt-1">{alerts.length === 0 ? 'all clear' : 'active'}</p>
        </div>
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold">Hot Nodes</p>
          <p className="text-2xl font-bold mt-1" style={{ color: clusters.some(c => c.hot_nodes > 0) ? '#F0AB00' : '#3E8635' }}>
            {clusters.reduce((s, c) => s + c.hot_nodes, 0)}
          </p>
          <p className="text-xs text-[#6A6E73] mt-1">overloaded nodes</p>
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="bg-[#212121] border border-[#C9190B]/30 rounded-lg p-4">
          <p className="text-xs text-[#C9190B] uppercase tracking-wider font-bold mb-3">Health Alerts</p>
          {alerts.map(a => (
            <div key={a.alert_id} className="flex items-center justify-between text-sm py-2 border-b border-[#1a1a1a] last:border-0">
              <div className="flex items-center gap-3">
                <StatusBadge status={a.severity} />
                <span className="text-white">{a.cluster_name}</span>
                <span className="text-xs bg-[#1a1a1a] text-[#6A6E73] px-2 py-0.5 rounded">{a.alert_type?.replace(/_/g, ' ') || 'unknown'}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[#6A6E73] text-xs">{a.recommended_action}</span>
                {a.created_at && <span className="text-[#6A6E73] text-xs font-mono">{new Date(a.created_at).toLocaleTimeString()}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Cluster Grid */}
      <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
        <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Cluster Capacity</p>
        {clusters.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-[#6A6E73] text-sm mb-2">No cluster data available</p>
            <p className="text-[#6A6E73] text-xs">Configure STARGATE_API_URL and enable SMART_PLACEMENT_ENABLED to see fleet capacity.</p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {clusters.map(c => {
              const hColor = c.health_status === 'healthy' ? '#3E8635' : c.health_status === 'degraded' ? '#F0AB00' : '#C9190B';
              const isSelected = selectedCluster === c.cluster_name;
              return (
                <div
                  key={c.cluster_name}
                  className={`border rounded-lg p-4 cursor-pointer transition ${isSelected ? 'border-[#0071C5] bg-[#0071C5]/10' : 'border-[#2e2e2e] hover:border-[#555]'}`}
                  style={{ borderLeftWidth: '3px', borderLeftColor: hColor }}
                  onClick={() => setSelectedCluster(isSelected ? null : c.cluster_name)}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: hColor }} />
                      <span className="text-sm font-medium text-white">{c.cluster_name}</span>
                    </div>
                    <span className="text-xs font-mono text-[#6A6E73]">
                      {c.last_updated ? `${Math.round((Date.now() - new Date(c.last_updated).getTime()) / 1000)}s ago` : ''}
                    </span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#6A6E73] w-14">Score</span>
                      <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${Math.min(100, c.score)}%`, backgroundColor: '#0071C5' }} />
                      </div>
                      <span className="text-xs font-mono text-[#6A6E73] w-8 text-right">{Math.round(c.score)}</span>
                    </div>
                    {c.cpu_utilization != null && (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-[#6A6E73] w-14">CPU</span>
                        <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${c.cpu_utilization * 100}%`, backgroundColor: c.cpu_utilization > 0.8 ? '#C9190B' : '#3E8635' }} />
                        </div>
                        <span className="text-xs font-mono text-[#6A6E73] w-8 text-right">{Math.round(c.cpu_utilization * 100)}%</span>
                      </div>
                    )}
                    <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-[#333]">
                      <div>
                        <p className="text-xs text-[#6A6E73]">Sandboxes</p>
                        <p className="text-sm font-medium text-white">{c.active_sandboxes}</p>
                      </div>
                      <div>
                        <p className="text-xs text-[#6A6E73]">VM/Node</p>
                        <p className="text-sm font-medium text-white">{c.vm_density != null ? c.vm_density.toFixed(1) : '—'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-[#6A6E73]">Health</p>
                        <p className="text-sm font-medium" style={{ color: (c.health_rate ?? 100) >= 80 ? '#3E8635' : '#F0AB00' }}>
                          {c.health_rate != null ? `${c.health_rate}%` : '—'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* DeepField Signals */}
      {selectedCluster && (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <p className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">
            DeepField Signals — {selectedCluster}
          </p>
          {signals.length === 0 ? (
            <p className="text-[#6A6E73] text-sm py-4 text-center">No signals available. Configure DEEPFIELD_API_URL to see fleet metrics.</p>
          ) : (
            <div className="space-y-2">
              {signals.map((s, i) => (
                <div key={i} className="flex items-center gap-3 py-2 border-b border-[#1a1a1a] last:border-0">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: s.status === 'critical' ? '#C9190B' : s.status === 'warning' ? '#F0AB00' : '#3E8635' }} />
                  <span className="text-sm text-white w-32">{s.metric_type.replace(/_/g, ' ')}</span>
                  <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{
                      width: `${Math.min(100, (s.value / (s.threshold || 1)) * 100)}%`,
                      backgroundColor: s.status === 'critical' ? '#C9190B' : s.status === 'warning' ? '#F0AB00' : '#0071C5',
                    }} />
                  </div>
                  <span className="text-xs font-mono text-[#6A6E73]">{s.value.toFixed(2)} / {s.threshold.toFixed(2)}</span>
                  <StatusBadge status={s.status} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
