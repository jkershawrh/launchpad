import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';
import { useBranding } from '../context/BrandingContext';
import StatusBadge from '../components/StatusBadge';

const DEMO_CATALOG_IDS = [
  'qs-rag-chatbot',
  'qs-llm-cpu-serving',
  'qs-vllm-tool-calling',
  'inference-overdrive',
  'enterprise-rag',
  'aiops-copilot',
  'governed-agent',
  'agent-swarm',
  'research-agent',
  'recovery-demo',
  'replay-comparison',
  'workload-generator',
  'training-demo',
  'full-platform-sandbox',
];

const CATEGORY_LABELS: Record<string, string> = {
  quick_start: 'Quick Start',
  guided_build: 'Guided Build',
  open_sandbox: 'Open Sandbox',
};

const CATEGORY_ACCENT: Record<string, string> = {
  quick_start: '#EE0000',
  guided_build: '#0068B5',
  open_sandbox: '#3E8635',
};

const CATEGORY_ICONS: Record<string, ReactNode> = {
  quick_start: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
  guided_build: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
    </svg>
  ),
  open_sandbox: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
    </svg>
  ),
};

export default function Demos() {
  const { profile } = useBranding();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [launching, setLaunching] = useState<string | null>(null);
  const [error, setError] = useState('');

  const primaryColor = profile?.primary_color || '#EE0000';
  const brandParam = searchParams.get('brand');
  const brandQuery = brandParam ? `?brand=${brandParam}` : '';

  useEffect(() => {
    api.listCatalog().then((data) => {
      const demoItems = data.filter((item) =>
        DEMO_CATALOG_IDS.includes(item.catalog_item_id)
      );
      setItems(demoItems);
      setLoading(false);
    });
  }, []);

  const filtered = filter === 'all' ? items : items.filter((i) => i.category === filter);

  const categories = ['all', 'quick_start', 'guided_build', 'open_sandbox'] as const;

  const handleLaunch = async (item: CatalogItem) => {
    setLaunching(item.catalog_item_id);
    setError('');

    try {
      const request = await api.createLabRequest({
        tenant_id: 'partner-oem-a',
        requester_id: 'demo-user',
        catalog_item_id: item.catalog_item_id,
        requested_mode: item.category,
        persistence: 'ephemeral',
        ttl: item.default_ttl || '4h',
        hardware_profile: item.default_hardware_profile || 'xeon-basic',
        quota_profile: item.default_quota_profile || 'standard',
      });

      if (request.status === 'rejected') {
        setError(`Request for "${item.display_name}" was rejected.`);
        setLaunching(null);
        return;
      }

      const session = await api.provisionLab(request.request_id);
      const validated = await api.validateSession(session.session_id);
      navigate(`/sessions/${validated.session_id}${brandQuery}`);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : `Failed to launch "${item.display_name}".`
      );
      setLaunching(null);
    }
  };

  return (
    <div>
      {/* Hero banner */}
      <section className="bg-[#151515] text-white py-16 px-6">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-3xl sm:text-4xl font-bold mb-3 tracking-tight">
            Demo Experiences
          </h1>
          <p className="text-gray-300 text-lg max-w-2xl leading-relaxed">
            Launch pre-built AI demo environments powered by Red Hat OpenShift
            and Intel hardware. Each demo provisions a full lab session with
            one click.
          </p>
        </div>
      </section>

      <div style={{ backgroundColor: primaryColor }} className="h-0.5" />

      <div className="max-w-6xl mx-auto px-6 py-10">
        {/* Category filter pills */}
        <div className="flex gap-2 mb-8 flex-wrap">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                filter === cat
                  ? 'bg-[#151515] text-white'
                  : 'bg-white text-[#6A6E73] border border-[#D2D2D2] hover:bg-gray-50'
              }`}
            >
              {cat === 'all' ? 'All Demos' : CATEGORY_LABELS[cat]}
            </button>
          ))}
        </div>

        {/* Error banner */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6 text-sm">
            {error}
          </div>
        )}

        {/* Loading state */}
        {loading ? (
          <p className="text-[#6A6E73]">Loading demos...</p>
        ) : filtered.length === 0 ? (
          <p className="text-[#6A6E73]">No demos found in this category.</p>
        ) : (
          /* Demo cards grid */
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filtered.map((item) => {
              const accent = CATEGORY_ACCENT[item.category] || primaryColor;
              const isLaunching = launching === item.catalog_item_id;

              return (
                <div
                  key={item.catalog_item_id}
                  className="bg-white rounded border border-[#D2D2D2] border-t-4 flex flex-col"
                  style={{ borderTopColor: accent }}
                >
                  <div className="p-6 flex-1 flex flex-col">
                    {/* Official badge + category */}
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-2">
                        <div style={{ color: accent }}>
                          {CATEGORY_ICONS[item.category]}
                        </div>
                        {(item.metadata?.official_quickstart as boolean) && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#EE0000] text-white uppercase tracking-wide">
                            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" /></svg>
                            Official
                          </span>
                        )}
                      </div>
                      <StatusBadge status={item.category} />
                    </div>

                    {/* Title and description */}
                    <h3 className="text-lg font-semibold text-[#151515] mb-2">
                      {item.display_name.replace(' — Official AI Quickstart', '')}
                    </h3>
                    <p className="text-[#6A6E73] text-sm leading-relaxed mb-4 flex-1">
                      {item.description}
                    </p>

                    {/* Capabilities */}
                    <div className="flex flex-wrap gap-1.5 mb-4">
                      {item.required_capabilities.slice(0, 3).map((cap) => (
                        <span
                          key={cap}
                          className="text-xs bg-[#F0F0F0] text-[#151515] px-2 py-0.5 rounded"
                        >
                          {cap}
                        </span>
                      ))}
                      {item.required_capabilities.length > 3 && (
                        <span className="text-xs text-[#6A6E73]">
                          +{item.required_capabilities.length - 3} more
                        </span>
                      )}
                    </div>

                    {/* Metadata row */}
                    <div className="flex gap-4 text-xs text-[#6A6E73] mb-5">
                      {item.default_hardware_profile && (
                        <span>{item.default_hardware_profile}</span>
                      )}
                      {item.default_ttl && <span>TTL: {item.default_ttl}</span>}
                      <span>v{item.version}</span>
                    </div>

                    {/* Launch button */}
                    <button
                      onClick={() => handleLaunch(item)}
                      disabled={isLaunching || launching !== null}
                      style={{
                        backgroundColor: isLaunching ? '#6A6E73' : primaryColor,
                      }}
                      className="w-full py-2.5 text-white rounded text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isLaunching ? 'Launching...' : 'Launch Demo'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Bottom CTA */}
        <div className="mt-12 bg-white border border-[#D2D2D2] rounded p-8 text-center">
          <h2 className="text-xl font-semibold text-[#151515] mb-2">
            Need your own environment?
          </h2>
          <p className="text-[#6A6E73] text-sm mb-4">
            Configure a custom sandbox with your choice of tools, access methods, and hardware.
          </p>
          <a
            href={`/sandbox${brandQuery}`}
            style={{ backgroundColor: primaryColor }}
            className="inline-block px-5 py-2.5 text-white rounded text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Open Sandbox
          </a>
        </div>
      </div>
    </div>
  );
}
