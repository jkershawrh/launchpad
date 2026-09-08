import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ClusterCapacity, DetailedSystemHealth } from '../api/types';
import StatusBadge from '../components/StatusBadge';

function formatCheckDetails(check: Record<string, string | number | boolean | undefined>): string {
  return Object.entries(check)
    .filter(([key, value]) => key !== 'status' && value !== undefined)
    .map(([key, value]) => `${key.replace(/_/g, ' ')}: ${String(value)}`)
    .join(' · ');
}

export default function SystemStatus() {
  const [health, setHealth] = useState<DetailedSystemHealth | null>(null);
  const [clusters, setClusters] = useState<ClusterCapacity[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [healthData, preflight] = await Promise.all([
        api.getDetailedSystemHealth(),
        api.getClusterPreflight(),
      ]);
      setHealth(healthData);
      setClusters(preflight.clusters);
      setLoadError('');
    } catch (err: unknown) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load platform health');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => void fetchData(), 0);
    intervalRef.current = window.setInterval(fetchData, 30000);
    return () => {
      window.clearTimeout(initialTimer);
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
  }, [fetchData]);

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading platform health...</div>;
  if (loadError && !health) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#C9190B]">Unable to load platform health: {loadError}</div>;

  const healthy = health?.status === 'ok';
  const eligibleClusters = clusters.filter((cluster) => cluster.eligible).length;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">System Status</h1>
      <p className="text-[#6A6E73] mb-8">Infrastructure health and execution cluster readiness.</p>

      {loadError && (
        <div className="bg-yellow-50 border border-yellow-300 text-yellow-900 rounded p-4 mb-6 text-sm">
          Refresh warning: {loadError}
        </div>
      )}

      <div className={`rounded border p-4 mb-8 flex items-center gap-3 ${
        healthy ? 'bg-green-50 border-green-300 text-green-800' : 'bg-red-50 border-red-300 text-red-800'
      }`}>
        <span className="text-xl">{healthy ? '✓' : '✗'}</span>
        <div>
          <p className="font-semibold text-sm">{healthy ? 'Platform checks passing' : 'Platform checks need attention'}</p>
          <p className="text-xs mt-0.5">
            {eligibleClusters}/{clusters.length} execution clusters eligible · refreshed {health?.timestamp ? new Date(health.timestamp).toLocaleTimeString() : '—'}
          </p>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        {Object.entries(health?.checks || {}).map(([name, check]) => (
          <div key={name} className="bg-white rounded border border-[#D2D2D2] p-5">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-[#6A6E73] uppercase font-medium">{name.replace(/_/g, ' ')}</p>
              <StatusBadge status={check.status} />
            </div>
            <p className="text-xs text-[#6A6E73] mt-3">{formatCheckDetails(check) || 'Check completed'}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded border border-[#D2D2D2] overflow-hidden">
        <div className="p-5 border-b border-[#D2D2D2]">
          <h2 className="text-sm font-semibold text-[#151515]">Execution clusters</h2>
          <p className="text-xs text-[#6A6E73] mt-1">Read-only placement preflight; inspection does not enable a cluster.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase bg-[#F0F0F0] border-b border-[#D2D2D2]">
                <th className="py-3 px-4">Cluster</th>
                <th className="py-3 px-4">Health</th>
                <th className="py-3 px-4">Placement</th>
                <th className="py-3 px-4">CPU free</th>
                <th className="py-3 px-4">Memory free</th>
                <th className="py-3 px-4">Pod slots</th>
                <th className="py-3 px-4">Reason</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((cluster) => (
                <tr key={cluster.cluster_id || cluster.cluster_name} className="border-b border-[#F0F0F0] last:border-0">
                  <td className="py-3 px-4">
                    <p className="font-medium text-[#151515]">{cluster.cluster_name}</p>
                    <p className="font-mono text-xs text-[#6A6E73]">{cluster.cluster_id || '—'}</p>
                  </td>
                  <td className="py-3 px-4"><StatusBadge status={cluster.health_status} /></td>
                  <td className="py-3 px-4"><StatusBadge status={cluster.eligible ? 'eligible' : 'disabled'} /></td>
                  <td className="py-3 px-4">{cluster.available_cpu_millicores == null ? '—' : `${(cluster.available_cpu_millicores / 1000).toFixed(1)} cores`}</td>
                  <td className="py-3 px-4">{cluster.available_memory_mib == null ? '—' : `${Math.round(cluster.available_memory_mib / 1024)} GiB`}</td>
                  <td className="py-3 px-4">{cluster.available_pods ?? '—'}</td>
                  <td className="py-3 px-4 text-xs text-[#6A6E73] max-w-xs">{cluster.reason || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
