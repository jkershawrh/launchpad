import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { HandoffPackage, LabSession, OrchestrationDecision, RepeatabilityReport, ShowbackRecord } from '../api/types';
import DecisionInsight from '../components/DecisionInsight';
import StatusBadge from '../components/StatusBadge';

export default function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<LabSession | null>(null);
  const [handoff, setHandoff] = useState<HandoffPackage | null>(null);
  const [showback, setShowback] = useState<ShowbackRecord | null>(null);
  const [report, setReport] = useState<RepeatabilityReport | null>(null);
  const [decision, setDecision] = useState<OrchestrationDecision | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    Promise.all([
      api.getSession(sessionId),
      api.getHandoff(sessionId).catch(() => null),
      api.getShowback(sessionId).catch(() => null),
      api.getRepeatabilityReport(sessionId).catch(() => null),
    ]).then(([s, h, sb, r]) => {
      setSession(s);
      setHandoff(h);
      setShowback(sb);
      setReport(r);
      setLoading(false);
      if (s?.request_id) {
        api.getDecision(s.request_id).then(setDecision).catch(() => null);
      }
    });
  }, [sessionId]);

  const handleAction = async (action: string) => {
    if (!sessionId) return;
    let updated: LabSession;
    switch (action) {
      case 'activate': updated = await api.activateSession(sessionId); break;
      case 'reset': updated = await api.resetSession(sessionId); break;
      case 'reclaim': updated = await api.reclaimSession(sessionId); break;
      default: return;
    }
    setSession(updated);
  };

  if (loading) return <div className="max-w-4xl mx-auto px-4 py-10 text-[#6A6E73]">Loading session...</div>;
  if (!session) return <div className="max-w-4xl mx-auto px-4 py-10 text-red-600">Session not found.</div>;

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-[#151515]">Lab Session</h1>
          <p className="text-gray-400 text-sm font-mono mt-1">{session.session_id}</p>
        </div>
        <StatusBadge status={session.status} />
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Details</h2>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-[#6A6E73]">Catalog Item</dt>
              <dd className="text-[#151515] font-medium">{session.catalog_item_id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#6A6E73]">Tenant</dt>
              <dd className="text-[#151515]">{session.tenant_id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#6A6E73]">Namespace</dt>
              <dd className="text-[#151515] font-mono text-xs">{session.namespace}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#6A6E73]">Expires</dt>
              <dd className="text-[#151515]">{session.expires_at ? new Date(session.expires_at).toLocaleString() : '—'}</dd>
            </div>
          </dl>
        </div>

        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">URLs</h2>
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-[#6A6E73] mb-1">Lab URL</dt>
              <dd>
                {session.lab_url ? (
                  <a href={session.lab_url} target="_blank" rel="noopener noreferrer" className="text-[#0068B5] hover:underline break-all">
                    {session.lab_url}
                  </a>
                ) : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-[#6A6E73] mb-1">Dashboard URL</dt>
              <dd>
                {session.dashboard_url ? (
                  <a href={session.dashboard_url} target="_blank" rel="noopener noreferrer" className="text-[#0068B5] hover:underline break-all">
                    {session.dashboard_url}
                  </a>
                ) : '—'}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Placement Decision */}
      <DecisionInsight decision={decision} />

      {/* Actions */}
      <div className="flex gap-3 mb-8">
        {session.status === 'ready' && (
          <button onClick={() => handleAction('activate')} className="px-4 py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700">
            Activate
          </button>
        )}
        {session.status === 'active' && (
          <button onClick={() => handleAction('reset')} className="px-4 py-2 bg-orange-500 text-white rounded text-sm hover:bg-orange-600">
            Reset
          </button>
        )}
        {(session.status === 'resetting' || session.status === 'expired') && (
          <button onClick={() => handleAction('reclaim')} className="px-4 py-2 bg-gray-600 text-white rounded text-sm hover:bg-gray-700">
            Reclaim
          </button>
        )}
      </div>

      {/* Validation Results */}
      {session.validation_results.length > 0 && (
        <div className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Validation Results</h2>
          <div className="space-y-2">
            {session.validation_results.map((vr) => (
              <div key={vr.validation_id} className="flex items-center justify-between text-sm py-2 border-b border-gray-50 last:border-0">
                <span className="text-gray-700">{vr.check_name}</span>
                <div className="flex items-center gap-2">
                  <span className="text-gray-400 text-xs">{vr.message}</span>
                  <StatusBadge status={vr.result} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Handoff */}
      {handoff && (
        <div className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Handoff Package</h2>
          <div className="text-sm space-y-2">
            <p><span className="text-[#6A6E73]">Lab:</span> <span className="font-medium">{handoff.lab_title}</span></p>
            <p><span className="text-[#6A6E73]">Tenant:</span> {handoff.tenant}</p>
            {handoff.access_instructions && (
              <div>
                <span className="text-[#6A6E73]">Access:</span>
                <p className="text-gray-700 mt-1">{handoff.access_instructions}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Showback */}
      {showback && (
        <div className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Showback</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-gray-400">Duration</p>
              <p className="text-lg font-semibold text-[#151515]">{(showback.duration_seconds / 3600).toFixed(1)}h</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">CPU</p>
              <p className="text-lg font-semibold text-[#151515]">{showback.cpu_used_estimate || '—'}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Memory</p>
              <p className="text-lg font-semibold text-[#151515]">{showback.memory_used_estimate || '—'}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Model Requests</p>
              <p className="text-lg font-semibold text-[#151515]">{showback.model_requests}</p>
            </div>
          </div>
        </div>
      )}

      {/* Repeatability Report */}
      {report && (
        <div className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Repeatability Report</h2>
          <div className="flex items-center gap-4 mb-4">
            <div className="text-3xl font-bold text-[#151515]">{report.repeatability_score}</div>
            <div className="text-sm text-[#6A6E73]">/ 100</div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
            {[
              { label: 'Catalog Versioned', ok: report.catalog_versioned },
              { label: 'Plan Generated', ok: report.provisioning_plan_generated },
              { label: 'Validation Passed', ok: report.validation_passed },
              { label: 'Handoff Generated', ok: report.handoff_generated },
              { label: 'Showback Generated', ok: report.showback_generated },
              { label: 'Cleanup Defined', ok: report.cleanup_defined },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2">
                <span className={item.ok ? 'text-green-600' : 'text-gray-300'}>{item.ok ? 'OK' : '--'}</span>
                <span className="text-gray-600">{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Lifecycle Events */}
      {session.lifecycle_events.length > 0 && (
        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Lifecycle Events</h2>
          <div className="space-y-2">
            {session.lifecycle_events.map((evt, i) => (
              <div key={i} className="flex items-center gap-3 text-sm py-1">
                <span className="text-gray-400 text-xs font-mono w-40 shrink-0">
                  {new Date(evt.timestamp).toLocaleTimeString()}
                </span>
                <StatusBadge status={evt.from_status} />
                <span className="text-gray-400">{"→"}</span>
                <StatusBadge status={evt.to_status} />
                {evt.reason && <span className="text-gray-400 text-xs ml-2">{evt.reason}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
