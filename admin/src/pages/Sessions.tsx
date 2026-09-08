import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem, LabSession } from '../api/types';
import StatusBadge from '../components/StatusBadge';

interface CatalogSessionGroup {
  catalogItemId: string;
  displayName: string;
  sessions: LabSession[];
  totalCount: number;
  reclaimableCount: number;
  latestActivity: number;
}

const sessionTime = (session: LabSession) => {
  const timestamps = [
    session.started_at,
    session.completed_at,
    session.lifecycle_events.at(-1)?.timestamp,
  ].filter((value): value is string => Boolean(value));
  return Math.max(0, ...timestamps.map((value) => new Date(value).getTime()));
};

function groupSessionsByCatalog(
  sessions: LabSession[],
  catalog: CatalogItem[],
): CatalogSessionGroup[] {
  const displayNames = new Map(catalog.map((item) => [item.catalog_item_id, item.display_name]));
  const grouped = new Map<string, LabSession[]>();
  sessions.forEach((session) => {
    const current = grouped.get(session.catalog_item_id) ?? [];
    current.push(session);
    grouped.set(session.catalog_item_id, current);
  });

  return [...grouped.entries()]
    .map(([catalogItemId, items]) => {
      const sorted = [...items].sort((a, b) => sessionTime(b) - sessionTime(a));
      return {
        catalogItemId,
        displayName: displayNames.get(catalogItemId) ?? catalogItemId,
        sessions: sorted,
        totalCount: sorted.length,
        reclaimableCount: sorted.filter((session) => session.status !== 'reclaimed').length,
        latestActivity: Math.max(0, ...sorted.map(sessionTime)),
      };
    })
    .sort((a, b) => b.latestActivity - a.latestActivity);
}

export default function Sessions() {
  const [sessions, setSessions] = useState<LabSession[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [filter, setFilter] = useState('all');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [reclaimingId, setReclaimingId] = useState<string | null>(null);
  const [reclaimingCatalog, setReclaimingCatalog] = useState<string | null>(null);

  const refreshSessions = async () => {
    setSessions(await api.listSessions(500));
  };

  useEffect(() => {
    Promise.all([
      api.listSessions(500),
      api.listCatalog().catch(() => [] as CatalogItem[]),
    ])
      .then(([sessionData, catalogData]) => {
        setSessions(sessionData);
        setCatalog(catalogData);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : 'Failed to load sessions');
      })
      .finally(() => setLoading(false));
  }, []);

  const handleForceReclaim = async (sessionId: string) => {
    if (!window.confirm(`Force reclaim session ${sessionId.slice(0, 8)}...? This cannot be undone.`)) return;
    setReclaimingId(sessionId);
    try {
      await api.forceReclaimSession(sessionId);
      await refreshSessions();
    } catch (err) {
      window.alert(`Failed to reclaim: ${err}`);
    } finally {
      setReclaimingId(null);
    }
  };

  const handleCatalogReclaim = async (group: CatalogSessionGroup) => {
    if (group.reclaimableCount === 0) return;
    const confirmed = window.confirm(
      `Force reclaim all ${group.reclaimableCount} non-reclaimed session(s) for “${group.displayName}”? `
      + 'This deletes every associated lab environment and cannot be undone.',
    );
    if (!confirmed) return;

    setReclaimingCatalog(group.catalogItemId);
    try {
      const result = await api.forceReclaimCatalog(group.catalogItemId);
      await refreshSessions();
      if (result.failed_count > 0) {
        window.alert(
          `Reclaimed ${result.reclaimed_count} session(s); ${result.failed_count} require attention.`,
        );
      }
    } catch (err) {
      window.alert(`Bulk force reclaim failed: ${err}`);
    } finally {
      setReclaimingCatalog(null);
    }
  };

  const groups = useMemo(() => {
    const allGroups = groupSessionsByCatalog(sessions, catalog);
    if (filter === 'all') return allGroups;
    return allGroups
      .map((group) => ({
        ...group,
        sessions: group.sessions.filter((session) => session.status === filter),
      }))
      .filter((group) => group.sessions.length > 0);
  }, [sessions, catalog, filter]);

  const toggleGroup = (catalogItemId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(catalogItemId)) next.delete(catalogItemId);
      else next.add(catalogItemId);
      return next;
    });
  };

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;
  if (loadError) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#C9190B]">Unable to load sessions: {loadError}</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">Sessions</h1>
      <p className="text-[#6A6E73] mb-8">
        Sessions are grouped by catalog item. Expand a group to inspect or reclaim individual labs.
      </p>

      <div className="flex gap-2 mb-6 flex-wrap">
        {['all', 'ready', 'active', 'provisioning', 'validating', 'failed', 'cleanup_failed', 'reclaimed'].map((value) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              filter === value
                ? 'bg-[#151515] text-white'
                : 'bg-white text-[#6A6E73] border border-[#D2D2D2] hover:bg-gray-50'
            }`}
          >
            {value === 'all'
              ? 'All'
              : value.split('_').map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
          </button>
        ))}
      </div>

      {groups.length === 0 ? (
        <div className="bg-white rounded border border-[#D2D2D2] p-8 text-center text-[#6A6E73]">
          No sessions found.
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((group) => {
            const isExpanded = expanded.has(group.catalogItemId);
            const isBulkReclaiming = reclaimingCatalog === group.catalogItemId;
            const statusCounts = group.sessions.reduce<Record<string, number>>((counts, session) => {
              counts[session.status] = (counts[session.status] ?? 0) + 1;
              return counts;
            }, {});
            return (
              <section
                key={group.catalogItemId}
                className="bg-white rounded border border-[#D2D2D2] overflow-hidden"
              >
                <div className="flex items-center gap-4 p-4">
                  <button
                    type="button"
                    aria-expanded={isExpanded}
                    aria-controls={`catalog-sessions-${group.catalogItemId}`}
                    onClick={() => toggleGroup(group.catalogItemId)}
                    className="flex flex-1 min-w-0 items-center gap-4 text-left"
                  >
                    <span className="text-[#0068B5] text-xl" aria-hidden="true">
                      {isExpanded ? '▾' : '▸'}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[#151515] font-semibold truncate">
                        {group.displayName}
                      </span>
                      <span className="block text-[#6A6E73] text-xs font-mono truncate">
                        {group.catalogItemId}
                      </span>
                    </span>
                  </button>
                  <div className="hidden md:flex items-center gap-2">
                    {Object.entries(statusCounts).map(([status, count]) => (
                      <span key={status} className="flex items-center gap-1">
                        <StatusBadge status={status} />
                        <span className="text-xs text-[#6A6E73]">{count}</span>
                      </span>
                    ))}
                  </div>
                  <span className="text-sm text-[#6A6E73] whitespace-nowrap">
                    {filter === 'all'
                      ? `${group.totalCount} lab${group.totalCount === 1 ? '' : 's'}`
                      : `${group.sessions.length} shown / ${group.totalCount} total`}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleCatalogReclaim(group)}
                    disabled={group.reclaimableCount === 0 || isBulkReclaiming || reclaimingCatalog !== null}
                    className="px-3 py-2 text-xs font-semibold rounded border border-[#C9190B] text-[#C9190B] hover:bg-[#C9190B] hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                  >
                    {isBulkReclaiming
                      ? 'Reclaiming group...'
                      : `Force Reclaim All (${group.reclaimableCount})`}
                  </button>
                </div>

                {isExpanded && (
                  <div id={`catalog-sessions-${group.catalogItemId}`} className="border-t border-[#D2D2D2] overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-[#6A6E73] text-xs uppercase bg-[#F0F0F0] border-b border-[#D2D2D2]">
                          <th className="py-3 px-4">Session</th>
                          <th className="py-3 px-4">Tenant</th>
                          <th className="py-3 px-4">Cluster</th>
                          <th className="py-3 px-4">Status</th>
                          <th className="py-3 px-4">Namespace</th>
                          <th className="py-3 px-4">Expires</th>
                          <th className="py-3 px-4">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.sessions.map((session) => (
                          <tr key={session.session_id} className="border-b border-[#F0F0F0] last:border-0 hover:bg-[#F0F0F0]/50">
                            <td className="py-3 px-4">
                              <Link to={`/sessions/${session.session_id}`} className="text-[#0068B5] hover:underline font-mono text-xs">
                                {session.session_id.slice(0, 8)}...
                              </Link>
                            </td>
                            <td className="py-3 px-4 text-[#151515]">{session.tenant_id}</td>
                            <td className="py-3 px-4 text-[#6A6E73]">{session.cluster_ref ?? '—'}</td>
                            <td className="py-3 px-4"><StatusBadge status={session.status} /></td>
                            <td className="py-3 px-4 font-mono text-xs text-[#6A6E73]">{session.namespace}</td>
                            <td className="py-3 px-4 text-[#6A6E73] text-xs">
                              {session.expires_at ? new Date(session.expires_at).toLocaleString() : '—'}
                            </td>
                            <td className="py-3 px-4">
                              {session.status !== 'reclaimed' && (
                                <button
                                  type="button"
                                  onClick={() => handleForceReclaim(session.session_id)}
                                  disabled={reclaimingId === session.session_id || reclaimingCatalog !== null}
                                  className="px-2 py-1 text-xs font-medium rounded border border-[#C9190B] text-[#C9190B] hover:bg-[#C9190B] hover:text-white transition-colors disabled:opacity-50"
                                >
                                  {reclaimingId === session.session_id ? 'Reclaiming...' : 'Force Reclaim'}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
