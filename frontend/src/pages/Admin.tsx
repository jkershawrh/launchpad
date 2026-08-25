import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { LabSession } from '../api/types';
import StatusBadge from '../components/StatusBadge';

interface ModelInventory {
  summary: { configured: number; running: number; exposed: number; healthy: number };
  models: Array<{
    id: string; display_name: string; namespace: string; hardware: string; use_case: string;
    desired_replicas: number; ready_replicas: number; litellm_exposed: boolean; status: string;
  }>;
}

export default function Admin() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [modelInventory, setModelInventory] = useState<ModelInventory | null>(null);

  useEffect(() => {
    api.listSessions().then((data) => {
      setSessions([...data].sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()));
      setLoading(false);
    });
    fetch('/api/admin/models', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : null)
      .then(setModelInventory)
      .catch(() => setModelInventory(null));
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

      <div className="bg-white rounded-lg border p-6 mb-8">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase">AI Model Portfolio</h2>
            <p className="text-sm text-gray-500 mt-1">Curated models configured on Oberon. Stopped models consume no serving capacity.</p>
          </div>
          <span className="text-xs text-gray-500 whitespace-nowrap">89 models discoverable in the RHOAI catalog</span>
        </div>
        {!modelInventory ? (
          <p className="text-sm text-gray-400">Model inventory is unavailable.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              {[
                ['Configured', modelInventory.summary.configured],
                ['Running', modelInventory.summary.running],
                ['LiteMaaS exposed', modelInventory.summary.exposed],
                ['End-to-end healthy', modelInventory.summary.healthy],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md bg-gray-50 border px-4 py-3">
                  <p className="text-xs uppercase text-gray-400">{label}</p>
                  <p className="text-2xl font-bold text-gray-900">{value}</p>
                </div>
              ))}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-gray-400 text-xs uppercase border-b">
                  <th className="pb-2 pr-4">Model</th><th className="pb-2 pr-4">Purpose</th><th className="pb-2 pr-4">Hardware</th><th className="pb-2 pr-4">Replicas</th><th className="pb-2">Status</th>
                </tr></thead>
                <tbody>{modelInventory.models.map(model => (
                  <tr key={model.id} className="border-b border-gray-50 last:border-0">
                    <td className="py-3 pr-4"><p className="font-medium text-gray-900">{model.display_name}</p><p className="font-mono text-xs text-gray-400">{model.namespace}</p></td>
                    <td className="py-3 pr-4 text-gray-600">{model.use_case}</td>
                    <td className="py-3 pr-4 text-gray-600">{model.hardware}</td>
                    <td className="py-3 pr-4 text-gray-600">{model.ready_replicas}/{model.desired_replicas}</td>
                    <td className="py-3"><span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${model.status === 'healthy' ? 'bg-green-100 text-green-700' : model.status === 'stopped' ? 'bg-gray-100 text-gray-600' : model.status === 'running_not_exposed' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>{model.status.replaceAll('_', ' ')}</span></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </>
        )}
      </div>

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
