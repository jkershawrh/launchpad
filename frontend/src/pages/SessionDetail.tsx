import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { useBranding } from '../context/BrandingContext';
import type { HandoffPackage, LabSession, OrchestrationDecision, RepeatabilityReport, ShowbackRecord } from '../api/types';
import StatusBadge from '../components/StatusBadge';
import DecisionInsight from '../components/DecisionInsight';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="ml-2 px-2 py-1 text-xs rounded border border-[#333] text-[#6A6E73] hover:bg-white/10 transition"
      title="Copy to clipboard"
    >
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}

function SandboxConnectionPanel({ session }: { session: LabSession }) {
  const { profile: brandingProfile } = useBranding();
  const primaryColor = brandingProfile?.primary_color || '#EE0000';

  const resources = session.resources || {};

  const webConsoleUrl = (resources.web_console_url as string) || 'http://localhost:6901';
  const sshHost = (resources.ssh_host as string) || 'localhost';
  const sshPort = (resources.ssh_port as string) || '2222';
  const sshUser = (resources.ssh_user as string) || 'lab-user';
  const vscodeUrl = (resources.vscode_url as string) || 'http://localhost:8443';
  const jupyterUrl = (resources.jupyter_url as string) || 'http://localhost:8888';

  const sshCommand = `ssh ${sshUser}@${sshHost} -p ${sshPort}`;

  const accessMethods = [
    {
      key: 'console',
      label: 'Open Console',
      description: 'Web-based terminal and desktop environment',
      url: webConsoleUrl,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      ),
      color: primaryColor,
    },
    {
      key: 'vscode',
      label: 'Open IDE',
      description: 'VS Code Server in your browser',
      url: vscodeUrl,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
      ),
      color: '#0068B5',
    },
    {
      key: 'jupyter',
      label: 'Open Notebooks',
      description: 'Jupyter notebooks for interactive development',
      url: jupyterUrl,
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
      ),
      color: '#E87F2B',
    },
  ];

  return (
    <div className="bg-[#151515] rounded-lg border border-[#3C3F42] p-6 mb-8">
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center"
          style={{ backgroundColor: primaryColor }}
        >
          <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">Connect to Your Sandbox</h2>
          <p className="text-sm text-[#6A6E73]">Choose your preferred access method</p>
        </div>
      </div>

      {/* Access method buttons */}
      <div className="grid sm:grid-cols-3 gap-3 mb-5">
        {accessMethods.map((method) => (
          <a
            key={method.key}
            href={method.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-4 py-3 rounded-lg text-white transition-all hover:scale-[1.02]"
            style={{ backgroundColor: method.color }}
          >
            {method.icon}
            <div>
              <div className="font-medium text-sm">{method.label}</div>
              <div className="text-xs opacity-80">{method.description}</div>
            </div>
          </a>
        ))}
      </div>

      {/* SSH connection */}
      <div className="bg-[#1E1E1E] rounded-lg p-4 border border-[#3C3F42]">
        <div className="flex items-center gap-2 mb-2">
          <svg className="w-4 h-4 text-[#6A6E73]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <span className="text-sm font-medium text-[#6A6E73]">SSH Connection</span>
        </div>
        <div className="flex items-center justify-between">
          <code className="text-sm text-green-400 font-mono">{sshCommand}</code>
          <CopyButton text={sshCommand} />
        </div>
      </div>
    </div>
  );
}

export default function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [session, setSession] = useState<LabSession | null>(null);
  const [handoff, setHandoff] = useState<HandoffPackage | null>(null);
  const [showback, setShowback] = useState<ShowbackRecord | null>(null);
  const [report, setReport] = useState<RepeatabilityReport | null>(null);
  const [decision, setDecision] = useState<OrchestrationDecision | null>(null);
  const [loading, setLoading] = useState(true);
  const [showApiKey, setShowApiKey] = useState(false);

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

  const isSandbox =
    session.catalog_item_id.startsWith('sandbox-') ||
    'sandbox_type' in session.resources;

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Lab Session</h1>
          <p className="text-[#6A6E73] text-sm font-mono mt-1">{session.session_id}</p>
        </div>
        <StatusBadge status={session.status} />
      </div>

      {/* Sandbox Connection Panel */}
      {isSandbox && <SandboxConnectionPanel session={session} />}

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <h2 className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Details</h2>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-[#6A6E73]">Catalog Item</dt>
              <dd className="text-white font-medium">{session.catalog_item_id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#6A6E73]">Tenant</dt>
              <dd className="text-white">{session.tenant_id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#6A6E73]">Namespace</dt>
              <dd className="text-white font-mono text-xs">{session.namespace}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#6A6E73]">Expires</dt>
              <dd className="text-white">{session.expires_at ? new Date(session.expires_at).toLocaleString() : '—'}</dd>
            </div>
            {session.maas_api_key && (
              <div className="flex justify-between items-center">
                <dt className="text-[#6A6E73]">MaaS API Key</dt>
                <dd className="flex items-center gap-1">
                  <span className="text-white font-mono text-xs">
                    {showApiKey ? session.maas_api_key : `${session.maas_api_key.slice(0, 14)}****...`}
                  </span>
                  <button
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="px-2 py-0.5 text-xs rounded border border-[#333] text-[#6A6E73] hover:bg-white/10 transition"
                  >
                    {showApiKey ? 'Hide' : 'Show'}
                  </button>
                  <CopyButton text={session.maas_api_key} />
                </dd>
              </div>
            )}
          </dl>
        </div>

        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <h2 className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">URLs</h2>
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
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4 mb-6">
          <h2 className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Validation Results</h2>
          <div className="space-y-2">
            {session.validation_results.map((vr) => (
              <div key={vr.validation_id} className="flex items-center justify-between text-sm py-2 border-b border-[#1a1a1a] last:border-0">
                <span className="text-[#e0e0e0]">{vr.check_name}</span>
                <div className="flex items-center gap-2">
                  <span className="text-[#6A6E73] text-xs">{vr.message}</span>
                  <StatusBadge status={vr.result} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Handoff */}
      {handoff && (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4 mb-6">
          <h2 className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Handoff Package</h2>
          <div className="text-sm space-y-2">
            <p><span className="text-[#6A6E73]">Lab:</span> <span className="font-medium">{handoff.lab_title}</span></p>
            <p><span className="text-[#6A6E73]">Tenant:</span> {handoff.tenant}</p>
            {handoff.access_instructions && (
              <div>
                <span className="text-[#6A6E73]">Access:</span>
                <p className="text-[#e0e0e0] mt-1">{handoff.access_instructions}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Showback */}
      {showback && (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4 mb-6">
          <h2 className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Showback</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-[#6A6E73]">Duration</p>
              <p className="text-lg font-semibold text-white">{(showback.duration_seconds / 3600).toFixed(1)}h</p>
            </div>
            <div>
              <p className="text-xs text-[#6A6E73]">CPU</p>
              <p className="text-lg font-semibold text-white">{showback.cpu_used_estimate || '—'}</p>
            </div>
            <div>
              <p className="text-xs text-[#6A6E73]">Memory</p>
              <p className="text-lg font-semibold text-white">{showback.memory_used_estimate || '—'}</p>
            </div>
            <div>
              <p className="text-xs text-[#6A6E73]">Model Requests</p>
              <p className="text-lg font-semibold text-white">{showback.model_requests}</p>
            </div>
          </div>
        </div>
      )}

      {/* Repeatability Report */}
      {report && (
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4 mb-6">
          <h2 className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Repeatability Report</h2>
          <div className="flex items-center gap-4 mb-4">
            <div className="text-3xl font-bold text-white">{report.repeatability_score}</div>
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
        <div className="bg-[#212121] border border-[#2e2e2e] rounded-lg p-4">
          <h2 className="text-xs text-[#6A6E73] uppercase tracking-wider font-bold mb-4">Lifecycle Events</h2>
          <div className="space-y-2">
            {session.lifecycle_events.map((evt, i) => (
              <div key={i} className="flex items-center gap-3 text-sm py-1">
                <span className="text-[#6A6E73] text-xs font-mono w-40 shrink-0">
                  {new Date(evt.timestamp).toLocaleTimeString()}
                </span>
                <StatusBadge status={evt.from_status} />
                <span className="text-[#6A6E73]">{"→"}</span>
                <StatusBadge status={evt.to_status} />
                {evt.reason && <span className="text-[#6A6E73] text-xs ml-2">{evt.reason}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
