import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ContainerInfo, SystemStatus as SystemStatusType } from '../api/types';
import StatusBadge from '../components/StatusBadge';

export default function SystemStatus() {
  const [status, setStatus] = useState<SystemStatusType | null>(null);
  const [containers, setContainers] = useState<ContainerInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [logPanel, setLogPanel] = useState<{ name: string; logs: string } | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [restartingContainer, setRestartingContainer] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [statusData, containerData] = await Promise.all([
        api.getSystemStatus(),
        api.listContainers(),
      ]);
      setStatus(statusData);
      setContainers(containerData);
    } catch {
      // keep existing data on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, 10000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData]);

  const handleViewLogs = async (name: string) => {
    if (logPanel?.name === name) {
      setLogPanel(null);
      return;
    }
    setLogLoading(true);
    try {
      const data = await api.getContainerLogs(name);
      setLogPanel({ name: data.name, logs: data.logs });
    } catch (err) {
      setLogPanel({ name, logs: `Error fetching logs: ${err}` });
    } finally {
      setLogLoading(false);
    }
  };

  const handleRestart = async (name: string) => {
    if (!window.confirm(`Restart container "${name}"? This may cause brief downtime.`)) return;
    setRestartingContainer(name);
    try {
      await api.restartContainer(name);
      await fetchData();
    } catch (err) {
      alert(`Failed to restart: ${err}`);
    } finally {
      setRestartingContainer(null);
    }
  };

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">System Status</h1>
      <p className="text-[#6A6E73] mb-8">Infrastructure health and container management.</p>

      {/* Health banner */}
      {status && (
        <div
          className={`rounded border p-4 mb-8 flex items-center gap-3 ${
            status.healthy
              ? 'bg-green-50 border-green-300 text-green-800'
              : 'bg-red-50 border-red-300 text-red-800'
          }`}
        >
          <span className="text-xl">{status.healthy ? '✓' : '✗'}</span>
          <div>
            <p className="font-semibold text-sm">
              {status.healthy ? 'All Systems Operational' : 'Issues Detected'}
            </p>
            <p className="text-xs mt-0.5">
              {status.containers} container{status.containers !== 1 ? 's' : ''} &middot;{' '}
              {status.active_sessions} active session{status.active_sessions !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid sm:grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded border border-[#D2D2D2] p-5">
          <p className="text-xs text-[#6A6E73] uppercase font-medium">Containers</p>
          <p className="text-3xl font-bold mt-1 text-[#151515]">{status?.containers ?? 0}</p>
        </div>
        <div className="bg-white rounded border border-[#D2D2D2] p-5">
          <p className="text-xs text-[#6A6E73] uppercase font-medium">Active Sessions</p>
          <p className="text-3xl font-bold mt-1 text-[#3E8635]">{status?.active_sessions ?? 0}</p>
        </div>
        <div className="bg-white rounded border border-[#D2D2D2] p-5">
          <p className="text-xs text-[#6A6E73] uppercase font-medium">Health</p>
          <p className={`text-3xl font-bold mt-1 ${status?.healthy ? 'text-[#3E8635]' : 'text-[#C9190B]'}`}>
            {status?.healthy ? 'OK' : 'ISSUE'}
          </p>
        </div>
      </div>

      {/* Containers table */}
      <div className="bg-white rounded border border-[#D2D2D2] overflow-hidden mb-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[#6A6E73] text-xs uppercase bg-[#F0F0F0] border-b border-[#D2D2D2]">
              <th className="py-3 px-4">Name</th>
              <th className="py-3 px-4">Image</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Ports</th>
              <th className="py-3 px-4">Uptime</th>
              <th className="py-3 px-4">CPU</th>
              <th className="py-3 px-4">Memory</th>
              <th className="py-3 px-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {containers.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-[#6A6E73]">
                  No containers found.
                </td>
              </tr>
            ) : (
              containers.map((c) => (
                <tr key={c.name} className="border-b border-[#F0F0F0] last:border-0 hover:bg-[#F0F0F0]/50">
                  <td className="py-3 px-4 font-mono text-xs text-[#151515]">{c.name}</td>
                  <td className="py-3 px-4 text-[#6A6E73] text-xs font-mono">{c.image}</td>
                  <td className="py-3 px-4"><StatusBadge status={c.status} /></td>
                  <td className="py-3 px-4 font-mono text-xs text-[#6A6E73]">{c.ports}</td>
                  <td className="py-3 px-4 text-xs text-[#6A6E73]">{c.uptime}</td>
                  <td className="py-3 px-4 text-xs text-[#151515]">{c.cpu_percent}</td>
                  <td className="py-3 px-4 text-xs text-[#151515]">{c.memory_usage}</td>
                  <td className="py-3 px-4">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleViewLogs(c.name)}
                        className="px-2 py-1 text-xs font-medium rounded border border-[#0068B5] text-[#0068B5] hover:bg-[#0068B5] hover:text-white transition-colors"
                      >
                        {logPanel?.name === c.name ? 'Hide Logs' : 'View Logs'}
                      </button>
                      <button
                        onClick={() => handleRestart(c.name)}
                        disabled={restartingContainer === c.name}
                        className="px-2 py-1 text-xs font-medium rounded border border-[#C9190B] text-[#C9190B] hover:bg-[#C9190B] hover:text-white transition-colors disabled:opacity-50"
                      >
                        {restartingContainer === c.name ? 'Restarting...' : 'Restart'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Log viewer */}
      {logLoading && (
        <div className="bg-[#1a1a1a] rounded border border-[#333] p-4 text-green-400 text-sm font-mono">
          Loading logs...
        </div>
      )}
      {logPanel && !logLoading && (
        <div className="bg-[#1a1a1a] rounded border border-[#333] overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 bg-[#252525] border-b border-[#333]">
            <span className="text-green-400 text-xs font-mono font-semibold">
              Logs: {logPanel.name}
            </span>
            <button
              onClick={() => setLogPanel(null)}
              className="text-gray-400 hover:text-white text-xs"
            >
              Close
            </button>
          </div>
          <pre className="p-4 text-green-400 text-xs font-mono overflow-auto max-h-96 whitespace-pre-wrap">
            {logPanel.logs || 'No logs available.'}
          </pre>
        </div>
      )}
    </div>
  );
}
