import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { LabSession } from '../api/types';
import StatusBadge from '../components/StatusBadge';

export default function Admin() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listSessions().then((data) => {
      setSessions(data);
      setLoading(false);
    });
  }, []);

  const activeSessions = sessions.filter((s) => ['ready', 'active', 'validating', 'provisioning'].includes(s.status));
  const failedSessions = sessions.filter((s) => ['failed', 'validation_failed'].includes(s.status));
  const expiringSessions = sessions.filter((s) => {
    if (!s.expires_at || s.status === 'reclaimed') return false;
    const exp = new Date(s.expires_at);
    const now = new Date();
    return exp.getTime() - now.getTime() < 2 * 60 * 60 * 1000;
  });

  const sessionsByTenant = sessions.reduce<Record<string, number>>((acc, s) => {
    acc[s.tenant_id] = (acc[s.tenant_id] || 0) + 1;
    return acc;
  }, {});

  if (loading) return <div className="max-w-6xl mx-auto px-4 py-10 text-gray-500">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto px-4 py-10">
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Admin / Reports</h1>
      <p className="text-gray-500 mb-8">Overview of lab sessions, usage, and tenant activity.</p>

      {/* Summary Cards */}
      <div className="grid sm:grid-cols-4 gap-4 mb-8">
        <div className="bg-white rounded-lg border p-5">
          <p className="text-xs text-gray-400 uppercase">Total Sessions</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{sessions.length}</p>
        </div>
        <div className="bg-white rounded-lg border p-5">
          <p className="text-xs text-gray-400 uppercase">Active</p>
          <p className="text-3xl font-bold text-green-600 mt-1">{activeSessions.length}</p>
        </div>
        <div className="bg-white rounded-lg border p-5">
          <p className="text-xs text-gray-400 uppercase">Failed</p>
          <p className="text-3xl font-bold text-red-600 mt-1">{failedSessions.length}</p>
        </div>
        <div className="bg-white rounded-lg border p-5">
          <p className="text-xs text-gray-400 uppercase">Expiring Soon</p>
          <p className="text-3xl font-bold text-orange-600 mt-1">{expiringSessions.length}</p>
        </div>
      </div>

      {/* Sessions by Tenant */}
      <div className="bg-white rounded-lg border p-6 mb-8">
        <h2 className="text-sm font-semibold text-gray-500 uppercase mb-4">Sessions by Tenant</h2>
        {Object.keys(sessionsByTenant).length === 0 ? (
          <p className="text-gray-400 text-sm">No sessions yet.</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(sessionsByTenant).map(([tenant, count]) => (
              <div key={tenant} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                <span className="text-sm text-gray-700">{tenant}</span>
                <span className="text-sm font-medium text-gray-900">{count} sessions</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* All Sessions Table */}
      <div className="bg-white rounded-lg border p-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase mb-4">All Sessions</h2>
        {sessions.length === 0 ? (
          <p className="text-gray-400 text-sm">No sessions yet. <Link to="/request" className="text-[#0071C5] hover:underline">Request a lab</Link> to get started.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 text-xs uppercase border-b">
                  <th className="pb-2 pr-4">Session</th>
                  <th className="pb-2 pr-4">Catalog Item</th>
                  <th className="pb-2 pr-4">Tenant</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2 pr-4">Namespace</th>
                  <th className="pb-2">Expires</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.session_id} className="border-b border-gray-50 last:border-0">
                    <td className="py-3 pr-4">
                      <Link to={`/sessions/${s.session_id}`} className="text-[#0071C5] hover:underline font-mono text-xs">
                        {s.session_id.slice(0, 8)}...
                      </Link>
                    </td>
                    <td className="py-3 pr-4 text-gray-700">{s.catalog_item_id}</td>
                    <td className="py-3 pr-4 text-gray-700">{s.tenant_id}</td>
                    <td className="py-3 pr-4"><StatusBadge status={s.status} /></td>
                    <td className="py-3 pr-4 font-mono text-xs text-gray-500">{s.namespace}</td>
                    <td className="py-3 text-gray-500 text-xs">
                      {s.expires_at ? new Date(s.expires_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
