import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { LabSession, ShowbackRecord } from '../api/types';

export default function Reports() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [showbacks, setShowbacks] = useState<Record<string, ShowbackRecord>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    api.listSessions(100)
      .then(async (data) => {
        setSessions(data);
        const records: Record<string, ShowbackRecord> = {};
        const results = await Promise.allSettled(data.map((session) => api.getShowback(session.session_id)));
        results.forEach((result, index) => {
          if (result.status === 'fulfilled') records[data[index].session_id] = result.value;
        });
        setShowbacks(records);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : 'Failed to load reports');
      })
      .finally(() => setLoading(false));
  }, []);

  const tenantSummaries = sessions.reduce<Record<string, {
    sessions: number;
    totalDuration: number;
    totalModelRequests: number;
    totalTokens: number;
  }>>((acc, s) => {
    if (!acc[s.tenant_id]) {
      acc[s.tenant_id] = { sessions: 0, totalDuration: 0, totalModelRequests: 0, totalTokens: 0 };
    }
    acc[s.tenant_id].sessions += 1;
    const sb = showbacks[s.session_id];
    if (sb) {
      acc[s.tenant_id].totalDuration += sb.duration_seconds;
      acc[s.tenant_id].totalModelRequests += sb.model_requests;
      acc[s.tenant_id].totalTokens += sb.estimated_tokens;
    }
    return acc;
  }, {});

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;
  if (loadError) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#C9190B]">Unable to load reports: {loadError}</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">Reports</h1>
      <p className="text-[#6A6E73] mb-8">Estimated showback for the 100 most recent sessions. Values remain estimates until measured per-seat telemetry is connected.</p>

      {Object.keys(tenantSummaries).length === 0 ? (
        <div className="bg-white rounded border border-[#D2D2D2] p-8 text-center text-[#6A6E73]">
          No usage data yet. Provision some labs to generate reports.
        </div>
      ) : (
        <>
          <div className="bg-white rounded border border-[#D2D2D2] p-6 mb-8">
            <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Showback by Tenant</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[#6A6E73] text-xs uppercase border-b border-[#D2D2D2]">
                    <th className="pb-2 pr-4">Tenant</th>
                    <th className="pb-2 pr-4">Sessions</th>
                    <th className="pb-2 pr-4">Total Duration</th>
                    <th className="pb-2 pr-4">Model Requests</th>
                    <th className="pb-2">Est. Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(tenantSummaries).map(([tenant, data]) => (
                    <tr key={tenant} className="border-b border-[#F0F0F0] last:border-0">
                      <td className="py-3 pr-4 text-[#151515] font-medium">{tenant}</td>
                      <td className="py-3 pr-4 text-[#151515]">{data.sessions}</td>
                      <td className="py-3 pr-4 text-[#151515]">{(data.totalDuration / 3600).toFixed(1)}h</td>
                      <td className="py-3 pr-4 text-[#151515]">{data.totalModelRequests.toLocaleString()}</td>
                      <td className="py-3 text-[#151515]">{data.totalTokens.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white rounded border border-[#D2D2D2] p-6">
            <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Session-Level Showback</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[#6A6E73] text-xs uppercase border-b border-[#D2D2D2]">
                    <th className="pb-2 pr-4">Session</th>
                    <th className="pb-2 pr-4">Tenant</th>
                    <th className="pb-2 pr-4">Catalog Item</th>
                    <th className="pb-2 pr-4">Duration</th>
                    <th className="pb-2 pr-4">CPU</th>
                    <th className="pb-2 pr-4">Memory</th>
                    <th className="pb-2">Model Req.</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(showbacks).map(([sessionId, sb]) => (
                    <tr key={sessionId} className="border-b border-[#F0F0F0] last:border-0">
                      <td className="py-3 pr-4 font-mono text-xs text-[#6A6E73]">{sessionId.slice(0, 8)}...</td>
                      <td className="py-3 pr-4 text-[#151515]">{sb.tenant_id}</td>
                      <td className="py-3 pr-4 text-[#151515]">{sb.catalog_item_id}</td>
                      <td className="py-3 pr-4 text-[#151515]">{(sb.duration_seconds / 3600).toFixed(1)}h</td>
                      <td className="py-3 pr-4 text-[#151515]">{sb.cpu_used_estimate || '—'}</td>
                      <td className="py-3 pr-4 text-[#151515]">{sb.memory_used_estimate || '—'}</td>
                      <td className="py-3 text-[#151515]">{sb.model_requests}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
