import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { LabSession } from '../api/types';
import StatusBadge from '../components/StatusBadge';

export default function Dashboard() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listSessions().then((data) => {
      setSessions(data);
      setLoading(false);
    });
  }, []);

  const active = sessions.filter((s) => ['ready', 'active', 'validating', 'provisioning'].includes(s.status));
  const failed = sessions.filter((s) => ['failed', 'validation_failed'].includes(s.status));
  const expiring = sessions.filter((s) => {
    if (!s.expires_at || s.status === 'reclaimed') return false;
    return new Date(s.expires_at).getTime() - Date.now() < 2 * 60 * 60 * 1000;
  });

  const tenantCounts = sessions.reduce<Record<string, number>>((acc, s) => {
    acc[s.tenant_id] = (acc[s.tenant_id] || 0) + 1;
    return acc;
  }, {});

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">Dashboard</h1>
      <p className="text-[#6A6E73] mb-8">Overview of lab sessions and platform health.</p>

      <div className="grid sm:grid-cols-4 gap-4 mb-8">
        {[
          { label: 'Total Sessions', value: sessions.length, color: 'text-[#151515]' },
          { label: 'Active', value: active.length, color: 'text-[#3E8635]' },
          { label: 'Failed', value: failed.length, color: 'text-[#C9190B]' },
          { label: 'Expiring Soon', value: expiring.length, color: 'text-[#F0AB00]' },
        ].map((card) => (
          <div key={card.label} className="bg-white rounded border border-[#D2D2D2] p-5">
            <p className="text-xs text-[#6A6E73] uppercase font-medium">{card.label}</p>
            <p className={`text-3xl font-bold mt-1 ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded border border-[#D2D2D2] p-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Sessions by Tenant</h2>
          {Object.keys(tenantCounts).length === 0 ? (
            <p className="text-[#6A6E73] text-sm">No sessions yet.</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(tenantCounts).map(([tenant, count]) => (
                <div key={tenant} className="flex items-center justify-between py-2 border-b border-[#F0F0F0] last:border-0">
                  <span className="text-sm text-[#151515]">{tenant}</span>
                  <span className="text-sm font-medium text-[#151515]">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white rounded border border-[#D2D2D2] p-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <Link to="/sessions" className="block text-sm text-[#0068B5] hover:underline">View all sessions</Link>
            <Link to="/tenants" className="block text-sm text-[#0068B5] hover:underline">Manage tenants</Link>
            <Link to="/reports" className="block text-sm text-[#0068B5] hover:underline">View showback reports</Link>
          </div>
        </div>
      </div>

      {sessions.length > 0 && (
        <div className="bg-white rounded border border-[#D2D2D2] p-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Recent Sessions</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase border-b border-[#D2D2D2]">
                <th className="pb-2 pr-4">Session</th>
                <th className="pb-2 pr-4">Catalog Item</th>
                <th className="pb-2 pr-4">Tenant</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {sessions.slice(0, 5).map((s) => (
                <tr key={s.session_id} className="border-b border-[#F0F0F0] last:border-0">
                  <td className="py-3 pr-4">
                    <Link to={`/sessions/${s.session_id}`} className="text-[#0068B5] hover:underline font-mono text-xs">
                      {s.session_id.slice(0, 8)}...
                    </Link>
                  </td>
                  <td className="py-3 pr-4 text-[#151515]">{s.catalog_item_id}</td>
                  <td className="py-3 pr-4 text-[#151515]">{s.tenant_id}</td>
                  <td className="py-3"><StatusBadge status={s.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
