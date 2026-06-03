import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useBranding } from '../context/BrandingContext';
import { api } from '../api/client';

interface FleetHealth {
  clusters: Array<{
    cluster_name: string;
    score: number;
    health_status: string;
    cpu_utilization?: number;
    gpu_available?: boolean;
  }>;
  alerts: Array<{
    alert_id: string;
    cluster_name: string;
    severity: string;
    recommended_action: string;
  }>;
}

interface FeedbackSummary {
  catalog_item_id: string;
  cluster_name: string;
  hardware_profile: string;
  total_attempts: number;
  success_rate: number;
  recommendation: string;
}

function HealthDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    healthy: '#3E8635',
    degraded: '#F0AB00',
    unhealthy: '#C9190B',
    unknown: '#6A6E73',
  };
  return (
    <span
      className="inline-block w-2 h-2 rounded-full mr-2"
      style={{ backgroundColor: colors[status] || colors.unknown }}
    />
  );
}

function ScoreBar({ value, color = '#0068B5' }: { value: number; color?: string }) {
  return (
    <div className="flex items-center gap-2 flex-1">
      <div className="flex-1 h-1.5 bg-[#F0F0F0] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, value)}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-mono text-[#6A6E73] w-8 text-right">{Math.round(value)}</span>
    </div>
  );
}

export default function Home() {
  const { profile } = useBranding();
  const [searchParams] = useSearchParams();
  const [fleet, setFleet] = useState<FleetHealth | null>(null);
  const [feedback, setFeedback] = useState<FeedbackSummary[]>([]);
  const [sessions, setSessions] = useState<{ active: number; total: number }>({ active: 0, total: 0 });

  const primaryColor = profile?.primary_color || '#EE0000';
  const headerBg = (profile?.metadata?.header_bg as string) || '#151515';
  const title = profile?.title || 'Partner AI Launchpad';
  const logoRefs = profile?.logo_refs || ['/logos/redhat.png', '/logos/intel.png'];
  const brandParam = searchParams.get('brand');
  const brandQuery = brandParam ? `?brand=${brandParam}` : '';

  useEffect(() => {
    fetch('/api/intelligence/fleet-health').then(r => r.ok ? r.json() : null).then(setFleet).catch(() => null);
    fetch('/api/admin/feedback/summary').then(r => r.ok ? r.json() : null).then(d => {
      if (d?.summaries) setFeedback(d.summaries);
    }).catch(() => null);
    api.listSessions().then(s => {
      const active = s.filter(x => ['ready', 'active', 'provisioning', 'validating'].includes(x.status)).length;
      setSessions({ active, total: s.length });
    }).catch(() => null);
  }, []);

  const clusters = fleet?.clusters || [];
  const alerts = fleet?.alerts || [];
  const healthyClusters = clusters.filter(c => c.health_status === 'healthy').length;
  const totalAttempts = feedback.reduce((s, f) => s + f.total_attempts, 0);
  const totalSuccess = feedback.reduce((s, f) => s + (f.success_rate * f.total_attempts), 0);
  const overallRate = totalAttempts > 0 ? Math.round((totalSuccess / totalAttempts) * 100) : 0;
  const avoidCount = feedback.filter(f => f.recommendation === 'avoid').length;

  return (
    <div>
      {/* Hero */}
      <section style={{ backgroundColor: headerBg }} className="text-white py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="flex justify-center items-center gap-6 mb-6">
            {logoRefs.map((logo, i) => (
              <span key={i} className="flex items-center gap-6">
                {i > 0 && <span className="text-white text-2xl font-bold mx-3">X</span>}
                <img src={logo} alt="" style={{ height: i === 0 ? '40px' : '30px', width: 'auto' }} />
              </span>
            ))}
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-center mb-3 tracking-tight">{title}</h1>
          <p className="text-center text-gray-400 max-w-xl mx-auto">
            Intelligent provisioning for AI demo environments on Intel hardware.
          </p>
        </div>
      </section>

      {/* Intelligence Overview */}
      <section className="max-w-5xl mx-auto px-6 -mt-8">
        <div className="grid sm:grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Active Sessions', value: sessions.active, color: '#3E8635' },
            { label: 'Fleet Clusters', value: clusters.length > 0 ? `${healthyClusters}/${clusters.length}` : '—', color: '#0068B5' },
            { label: 'Success Rate', value: totalAttempts > 0 ? `${overallRate}%` : '—', color: overallRate >= 80 ? '#3E8635' : '#F0AB00' },
            { label: 'Avoid-Listed', value: avoidCount, color: avoidCount > 0 ? '#C9190B' : '#3E8635' },
          ].map(card => (
            <div key={card.label} className="bg-white rounded-lg border border-[#D2D2D2] p-5 shadow-sm">
              <p className="text-xs text-[#6A6E73] uppercase font-medium">{card.label}</p>
              <p className="text-2xl font-bold mt-1" style={{ color: card.color }}>{card.value}</p>
            </div>
          ))}
        </div>

        {/* Alerts */}
        {alerts.length > 0 && (
          <div className="bg-white rounded-lg border border-[#D2D2D2] border-l-4 border-l-[#C9190B] p-4 mb-6">
            <p className="text-xs text-[#6A6E73] uppercase font-medium mb-2">Health Alerts</p>
            {alerts.map(a => (
              <div key={a.alert_id} className="flex items-center justify-between text-sm py-1">
                <span className="text-[#151515]">{a.cluster_name}</span>
                <span className="text-[#6A6E73] text-xs">{a.recommended_action}</span>
              </div>
            ))}
          </div>
        )}

        {/* Fleet + Actions row */}
        <div className="grid md:grid-cols-2 gap-6 mb-8">
          {/* Cluster Health */}
          <div className="bg-white rounded-lg border border-[#D2D2D2] p-6">
            <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Fleet Health</h2>
            {clusters.length === 0 ? (
              <p className="text-sm text-[#6A6E73]">No cluster data available. Enable SMART_PLACEMENT_ENABLED and configure STARGATE_API_URL.</p>
            ) : (
              <div className="space-y-3">
                {clusters.map(c => (
                  <div key={c.cluster_name} className="flex items-center gap-3">
                    <HealthDot status={c.health_status} />
                    <span className="text-sm text-[#151515] w-32 truncate">{c.cluster_name}</span>
                    <ScoreBar
                      value={c.score}
                      color={c.health_status === 'healthy' ? '#0068B5' : '#C9190B'}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Actions */}
          <div className="bg-white rounded-lg border border-[#D2D2D2] p-6">
            <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">Get Started</h2>
            <div className="space-y-3">
              <Link
                to={`/demos${brandQuery}`}
                className="flex items-center gap-3 px-4 py-3 rounded-lg text-white transition-all hover:opacity-90"
                style={{ backgroundColor: primaryColor }}
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <div>
                  <div className="font-medium text-sm">Launch a Demo</div>
                  <div className="text-xs opacity-80">10 custom demos + 7 AI quickstarts</div>
                </div>
              </Link>
              <Link
                to={`/sandbox${brandQuery}`}
                className="flex items-center gap-3 px-4 py-3 rounded-lg border border-[#D2D2D2] text-[#151515] hover:bg-[#F0F0F0] transition-colors"
              >
                <svg className="w-5 h-5 text-[#0068B5]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                </svg>
                <div>
                  <div className="font-medium text-sm">Open a Sandbox</div>
                  <div className="text-xs text-[#6A6E73]">Configurable environments with full hardware access</div>
                </div>
              </Link>
              <Link
                to={`/catalog${brandQuery}`}
                className="flex items-center gap-3 px-4 py-3 rounded-lg border border-[#D2D2D2] text-[#151515] hover:bg-[#F0F0F0] transition-colors"
              >
                <svg className="w-5 h-5 text-[#3E8635]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                </svg>
                <div>
                  <div className="font-medium text-sm">Browse Catalog</div>
                  <div className="text-xs text-[#6A6E73]">25 catalog items across 3 categories</div>
                </div>
              </Link>
            </div>
          </div>
        </div>

        {/* Intelligence Pipeline */}
        <div className="bg-white rounded-lg border border-[#D2D2D2] p-6 mb-8">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">How It Works</h2>
          <div className="flex justify-center gap-2 text-xs sm:text-sm overflow-x-auto">
            {[
              { step: 'Request', color: '#6A6E73' },
              { step: 'Classify', color: '#0068B5' },
              { step: 'Place', color: '#0068B5' },
              { step: 'Provision', color: '#3E8635' },
              { step: 'Validate', color: '#3E8635' },
              { step: 'Learn', color: '#E67E22' },
              { step: 'Ready', color: '#3E8635' },
            ].map((s, i) => (
              <div key={s.step} className="flex items-center gap-2 shrink-0">
                <span
                  className="px-3 py-1.5 rounded font-medium whitespace-nowrap text-white"
                  style={{ backgroundColor: s.color }}
                >
                  {s.step}
                </span>
                {i < 6 && <span className="text-[#D2D2D2]">{"→"}</span>}
              </div>
            ))}
          </div>
          <p className="text-center text-xs text-[#6A6E73] mt-3">
            Every demo is classified, placed on the best cluster, provisioned, validated, and the outcome feeds back into future decisions.
          </p>
        </div>
      </section>
    </div>
  );
}
