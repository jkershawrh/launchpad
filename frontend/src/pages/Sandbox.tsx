import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { useBranding } from '../context/BrandingContext';
import type { CatalogItem, Tenant } from '../api/types';
import { resolveOpenSandbox } from '../sandboxContract';

const SANDBOX_PRESETS = [
  {
    id: 'sandbox-minimal',
    label: 'Minimal',
    description: 'OpenShift Console and web terminal with oc, kubectl, and Helm.',
    stack: 'minimal',
    access: ['openshift_console', 'web_terminal'],
    aap: 'none',
  },
  {
    id: 'sandbox-ai-dev',
    label: 'OpenShift Developer',
    description: 'Namespace-scoped OpenShift Console, web terminal, browser IDE, and model endpoint access.',
    stack: 'ai_dev',
    access: ['openshift_console', 'web_terminal', 'vscode'],
    aap: 'playbook_library',
  },
  {
    id: 'sandbox-full-stack',
    label: 'Automation & GitOps',
    description: 'OpenShift development plus Ansible playbooks and Pipelines/GitOps tooling when available.',
    stack: 'full_redhat_ai',
    access: ['openshift_console', 'web_terminal', 'vscode', 'api'],
    aap: 'full_aap',
  },
  {
    id: 'sandbox-custom',
    label: 'Custom',
    description: 'Configure exactly what you need.',
    stack: 'minimal',
    access: ['openshift_console', 'web_terminal'],
    aap: 'none',
  },
];

const OBERON_CAPABILITIES = [
  'Red Hat OpenShift AI',
  'OpenShift Serverless',
  'OpenShift Service Mesh',
  'Cluster Observability',
  'Argo CD / GitOps',
  'Intel Device Plugins',
];

export default function Sandbox() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { profile: brandingProfile } = useBranding();

  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [catalogs, setCatalogs] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const [selectedPreset, setSelectedPreset] = useState('sandbox-ai-dev');
  const [isCustom, setIsCustom] = useState(false);

  const [form, setForm] = useState({
    tenant_id: '',
    requester_id: '',
    persistence: 'persistent' as 'ephemeral' | 'persistent',
    ttl: '8h',
    hardware_profile: 'gaudi-endpoint',
    quota_profile: 'standard',
    branding_profile_id: '',
  });

  const [sandboxConfig, setSandboxConfig] = useState({
    stack_level: 'ai_dev',
    access_methods: ['openshift_console', 'web_terminal', 'vscode'] as string[],
    aap_integration: 'playbook_library',
    storage_size: '50Gi',
  });

  const primaryColor = brandingProfile?.primary_color || '#EE0000';
  const brandParam = searchParams.get('brand');
  const brandQuery = brandParam ? `?brand=${brandParam}` : '';

  useEffect(() => {
    Promise.all([api.listTenants(), api.listCatalog()]).then(
      ([tens, cats]) => {
        setTenants(tens);
        setCatalogs(cats);
        const sandbox = resolveOpenSandbox(cats);
        const defaultTenant = tens.find((tenant) => tenant.status === 'active');
        setForm((current) => ({
          ...current,
          tenant_id: current.tenant_id || defaultTenant?.tenant_id || '',
          hardware_profile: sandbox?.default_hardware_profile || current.hardware_profile,
          quota_profile: sandbox?.default_quota_profile || current.quota_profile,
          ttl: sandbox?.default_ttl || current.ttl,
        }));
        setLoading(false);
      }
    );
  }, []);

  const handlePresetSelect = (presetId: string) => {
    setSelectedPreset(presetId);
    const preset = SANDBOX_PRESETS.find((p) => p.id === presetId);
    if (preset) {
      setIsCustom(presetId === 'sandbox-custom');
      setSandboxConfig({
        stack_level: preset.stack,
        access_methods: [...preset.access],
        aap_integration: preset.aap,
        storage_size: preset.stack === 'full_redhat_ai' ? '200Gi' : preset.stack === 'ai_dev' ? '50Gi' : '20Gi',
      });
      const catalogItem = catalogs.find((c) => c.catalog_item_id === presetId);
      if (catalogItem) {
        setForm((f) => ({
          ...f,
          hardware_profile: catalogItem.default_hardware_profile || f.hardware_profile,
          quota_profile: catalogItem.default_quota_profile || f.quota_profile,
          ttl: catalogItem.default_ttl || f.ttl,
        }));
      }
    }
  };

  const handleAccessMethodToggle = (method: string) => {
    setSandboxConfig((prev) => ({
      ...prev,
      access_methods: prev.access_methods.includes(method)
        ? prev.access_methods.filter((m) => m !== method)
        : [...prev.access_methods, method],
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');

    try {
      const sandboxCatalog = resolveOpenSandbox(catalogs);
      if (!sandboxCatalog) {
        setError('No active open sandbox is available in the catalog.');
        setSubmitting(false);
        return;
      }
      const request = await api.createLabRequest({
        ...form,
        catalog_item_id: sandboxCatalog.catalog_item_id,
        requested_mode: 'open_sandbox',
        metadata: { sandbox_config: sandboxConfig },
      });

      if (request.status === 'rejected') {
        setError('Request was rejected. Check your configuration.');
        setSubmitting(false);
        return;
      }

      const session = await api.provisionLab(request.request_id);
      const validated = await api.validateSession(session.session_id);
      navigate(`/sessions/${validated.session_id}${brandQuery}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create sandbox');
      setSubmitting(false);
    }
  };

  if (loading) return <div className="max-w-3xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;

  return (
    <div>
      <section className="bg-[#151515] text-white py-16 px-6">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-3xl sm:text-4xl font-bold mb-3 tracking-tight">Open Sandbox</h1>
          <p className="text-gray-300 text-lg leading-relaxed">
            Work directly in OpenShift with namespace-scoped access, Red Hat tooling, and optional automation capabilities.
          </p>
        </div>
      </section>

      <div style={{ backgroundColor: primaryColor }} className="h-0.5" />

      <div className="max-w-3xl mx-auto px-6 py-10">
        {error && (
          <div className="bg-[#C9190B]/10 border border-[#C9190B]/30 text-[#C9190B] px-4 py-3 rounded mb-6 text-sm">
            {error}
          </div>
        )}

        <section className="mb-8 rounded border border-[#333] bg-[#212121] p-5">
          <h2 className="text-sm font-semibold text-white">Available on the shared Oberon platform</h2>
          <p className="mt-1 text-xs leading-5 text-[#A3A3A3]">Your sandbox receives a private namespace and access to applicable cluster services. Operators remain centrally managed.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {OBERON_CAPABILITIES.map((capability) => <span key={capability} className="rounded-full border border-[#555] px-3 py-1 text-xs text-[#D2D2D2]">{capability}</span>)}
          </div>
        </section>

        {/* Preset Selection */}
        <h2 className="text-lg font-semibold text-white mb-4">Choose a Starting Point</h2>
        <div className="grid sm:grid-cols-2 gap-4 mb-10">
          {SANDBOX_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => handlePresetSelect(preset.id)}
              className={`text-left p-5 rounded border-2 transition-all ${
                selectedPreset === preset.id
                  ? 'border-[#0068B5] bg-[#0068B5]/15'
                  : 'border-[#333] bg-[#212121] hover:border-[#555]'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-white">{preset.label}</span>
                {selectedPreset === preset.id && (
                  <span className="w-5 h-5 rounded-full bg-[#0068B5] flex items-center justify-center">
                    <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                      <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                )}
              </div>
              <p className="text-sm text-[#6A6E73]">{preset.description}</p>
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Identity */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[#e0e0e0] mb-1">Tenant</label>
              <select
                value={form.tenant_id}
                onChange={(e) => setForm({ ...form, tenant_id: e.target.value })}
                className="w-full border border-[#333] rounded px-3 py-2 text-sm"
                required
              >
                <option value="">Select tenant...</option>
                {tenants.filter((t) => t.status === 'active').map((t) => (
                  <option key={t.tenant_id} value={t.tenant_id}>{t.display_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-[#e0e0e0] mb-1">OpenShift Username</label>
              <input
                type="text"
                value={form.requester_id}
                onChange={(e) => setForm({ ...form, requester_id: e.target.value })}
                placeholder="e.g., jane.doe"
                className="w-full border border-[#333] rounded px-3 py-2 text-sm"
                required
              />
              <p className="mt-1 text-xs text-[#6A6E73]">Used to grant edit access only to your new sandbox namespace.</p>
            </div>
          </div>

          {/* Configuration — always visible for custom, summary for presets */}
          {(isCustom || selectedPreset === 'sandbox-custom') && (
            <div className="border border-[#333] rounded p-6 bg-[#212121] space-y-5">
              <h3 className="text-sm font-semibold text-[#6A6E73] uppercase">Configuration</h3>

              <div>
                <label className="block text-sm font-medium text-[#e0e0e0] mb-1">Stack Level</label>
                <select
                  value={sandboxConfig.stack_level}
                  onChange={(e) => setSandboxConfig({ ...sandboxConfig, stack_level: e.target.value })}
                  className="w-full border border-[#333] rounded px-3 py-2 text-sm"
                >
                  <option value="minimal">Minimal — RHEL base, oc, podman, Python</option>
                  <option value="ai_dev">OpenShift Developer — oc, browser IDE, model endpoint</option>
                  <option value="full_redhat_ai">Automation &amp; GitOps — Ansible, Pipelines, GitOps tooling</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-[#e0e0e0] mb-2">Access Methods</label>
                <div className="flex flex-wrap gap-3">
                  {[
                    { value: 'openshift_console', label: 'OpenShift Console' },
                    { value: 'web_terminal', label: 'Web Terminal' },
                    { value: 'vscode', label: 'VS Code Server' },
                    { value: 'api', label: 'API' },
                  ].map((method) => (
                    <label
                      key={method.value}
                      className={`flex items-center gap-2 px-3 py-2 rounded border text-sm cursor-pointer transition-colors ${
                        sandboxConfig.access_methods.includes(method.value)
                          ? 'border-[#0068B5] bg-[#0068B5]/15 text-[#0068B5]'
                          : 'border-[#333] text-[#e0e0e0] hover:border-[#555]'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={sandboxConfig.access_methods.includes(method.value)}
                        onChange={() => handleAccessMethodToggle(method.value)}
                        className="sr-only"
                      />
                      {method.label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#e0e0e0] mb-1">AAP</label>
                  <select
                    value={sandboxConfig.aap_integration}
                    onChange={(e) => setSandboxConfig({ ...sandboxConfig, aap_integration: e.target.value })}
                    className="w-full border border-[#333] rounded px-3 py-2 text-sm"
                  >
                    <option value="none">None</option>
                    <option value="playbook_library">Playbooks</option>
                    <option value="full_aap">Full AAP</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#e0e0e0] mb-1">Storage</label>
                  <select
                    value={sandboxConfig.storage_size}
                    onChange={(e) => setSandboxConfig({ ...sandboxConfig, storage_size: e.target.value })}
                    className="w-full border border-[#333] rounded px-3 py-2 text-sm"
                  >
                    <option value="20Gi">20 GB</option>
                    <option value="50Gi">50 GB</option>
                    <option value="200Gi">200 GB</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#e0e0e0] mb-1">TTL</label>
                  <select
                    value={form.ttl}
                    onChange={(e) => setForm({ ...form, ttl: e.target.value })}
                    className="w-full border border-[#333] rounded px-3 py-2 text-sm"
                  >
                    <option value="4h">4 hours</option>
                    <option value="8h">8 hours</option>
                    <option value="12h">12 hours</option>
                    <option value="24h">24 hours</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Summary for non-custom presets */}
          {!isCustom && selectedPreset !== 'sandbox-custom' && (
            <div className="border border-[#333] rounded p-5 bg-[#212121]">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-[#6A6E73] uppercase">Your Sandbox</h3>
                <button
                  type="button"
                  onClick={() => { setSelectedPreset('sandbox-custom'); setIsCustom(true); }}
                  className="text-xs text-[#0068B5] hover:underline"
                >
                  Customize
                </button>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                <div>
                  <span className="text-[#6A6E73] text-xs block">Stack</span>
                  <span className="text-white font-medium">{sandboxConfig.stack_level.replace('_', ' ')}</span>
                </div>
                <div>
                  <span className="text-[#6A6E73] text-xs block">Access</span>
                  <span className="text-white font-medium">{sandboxConfig.access_methods.length} methods</span>
                </div>
                <div>
                  <span className="text-[#6A6E73] text-xs block">AAP</span>
                  <span className="text-white font-medium">{sandboxConfig.aap_integration.replace('_', ' ')}</span>
                </div>
                <div>
                  <span className="text-[#6A6E73] text-xs block">Storage</span>
                  <span className="text-white font-medium">{sandboxConfig.storage_size}</span>
                </div>
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            style={{ backgroundColor: primaryColor }}
            className="w-full py-3 text-white rounded font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Provisioning Sandbox...' : 'Launch Sandbox'}
          </button>
        </form>
      </div>
    </div>
  );
}
