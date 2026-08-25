import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { LabSession } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import { newestSessionsFirst } from '../sessionSort';

export default function Sessions() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listSessions().then((items) => setSessions(newestSessionsFirst(items))).finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">My labs</h1>
          <p className="mt-1 text-sm text-[#6A6E73]">Access current environments and review lifecycle records.</p>
        </div>
        <Link to="/request" className="rounded bg-[#EE0000] px-4 py-2 text-sm font-semibold text-white">Request a lab</Link>
      </div>
      <div className="mt-6 overflow-hidden rounded border border-[#333] bg-[#212121]">
        {loading ? <p className="p-6 text-sm text-[#6A6E73]">Loading labs…</p> : sessions.length === 0 ? (
          <p className="p-6 text-sm text-[#6A6E73]">No lab sessions yet.</p>
        ) : sessions.map((session) => (
          <Link key={session.session_id} to={`/sessions/${session.session_id}`} className="grid gap-3 border-b border-[#333] px-5 py-4 last:border-0 hover:bg-white/5 md:grid-cols-[1.3fr_1fr_auto_auto] md:items-center">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-white">{session.catalog_item_id}</p>
              <p className="truncate font-mono text-xs text-[#6A6E73]">{session.session_id}</p>
            </div>
            <p className="truncate font-mono text-xs text-[#A3A3A3]">{session.namespace || 'Namespace pending'}</p>
            <StatusBadge status={session.status} />
            <p className="text-xs text-[#A3A3A3]">{session.expires_at ? new Date(session.expires_at).toLocaleString() : 'No expiry'}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
