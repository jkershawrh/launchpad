import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { LabSession } from '../api/types';
import StatusBadge from '../components/StatusBadge';

export default function Sessions() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [reclaimingId, setReclaimingId] = useState<string | null>(null);

  useEffect(() => {
    api.listSessions().then((data) => {
      setSessions(data);
      setLoading(false);
    });
  }, []);

  const refreshSessions = () => {
    api.listSessions().then((data) => setSessions(data));
  };

  const handleForceReclaim = async (sessionId: string) => {
    if (!window.confirm(`Force reclaim session ${sessionId.slice(0, 8)}...? This cannot be undone.`)) return;
    setReclaimingId(sessionId);
    try {
      await api.forceReclaimSession(sessionId);
      refreshSessions();
    } catch (err) {
      alert(`Failed to reclaim: ${err}`);
    } finally {
      setReclaimingId(null);
    }
  };

  const filtered = filter === 'all'
    ? sessions
    : sessions.filter((s) => s.status === filter);

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">Sessions</h1>
      <p className="text-[#6A6E73] mb-8">All lab sessions across tenants.</p>

      <div className="flex gap-2 mb-6">
        {['all', 'ready', 'active', 'failed', 'reclaimed'].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              filter === f
                ? 'bg-[#151515] text-white'
                : 'bg-white text-[#6A6E73] border border-[#D2D2D2] hover:bg-gray-50'
            }`}
          >
            {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="bg-white rounded border border-[#D2D2D2] p-8 text-center text-[#6A6E73]">
          No sessions found.
        </div>
      ) : (
        <div className="bg-white rounded border border-[#D2D2D2] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase bg-[#F0F0F0] border-b border-[#D2D2D2]">
                <th className="py-3 px-4">Session</th>
                <th className="py-3 px-4">Catalog Item</th>
                <th className="py-3 px-4">Tenant</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Namespace</th>
                <th className="py-3 px-4">Expires</th>
                <th className="py-3 px-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.session_id} className="border-b border-[#F0F0F0] last:border-0 hover:bg-[#F0F0F0]/50">
                  <td className="py-3 px-4">
                    <Link to={`/sessions/${s.session_id}`} className="text-[#0068B5] hover:underline font-mono text-xs">
                      {s.session_id.slice(0, 8)}...
                    </Link>
                  </td>
                  <td className="py-3 px-4 text-[#151515]">{s.catalog_item_id}</td>
                  <td className="py-3 px-4 text-[#151515]">{s.tenant_id}</td>
                  <td className="py-3 px-4"><StatusBadge status={s.status} /></td>
                  <td className="py-3 px-4 font-mono text-xs text-[#6A6E73]">{s.namespace}</td>
                  <td className="py-3 px-4 text-[#6A6E73] text-xs">
                    {s.expires_at ? new Date(s.expires_at).toLocaleString() : '—'}
                  </td>
                  <td className="py-3 px-4">
                    {s.status !== 'reclaimed' && (
                      <button
                        onClick={() => handleForceReclaim(s.session_id)}
                        disabled={reclaimingId === s.session_id}
                        className="px-2 py-1 text-xs font-medium rounded border border-[#C9190B] text-[#C9190B] hover:bg-[#C9190B] hover:text-white transition-colors disabled:opacity-50"
                      >
                        {reclaimingId === s.session_id ? 'Reclaiming...' : 'Force Reclaim'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
