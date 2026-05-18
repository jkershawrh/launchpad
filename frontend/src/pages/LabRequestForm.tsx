import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { useBranding } from '../context/BrandingContext';
import type { BrandingProfile, CatalogItem, Tenant } from '../api/types';

export default function LabRequestForm() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { profile: brandingProfile } = useBranding();

  const [catalogs, setCatalogs] = useState<CatalogItem[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [brandings, setBrandings] = useState<BrandingProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const [form, setForm] = useState({
    tenant_id: '',
    requester_id: '',
    catalog_item_id: searchParams.get('catalog_item') || '',
    persistence: 'ephemeral' as 'ephemeral' | 'persistent',
    ttl: '4h',
    hardware_profile: '',
    quota_profile: 'standard',
    branding_profile_id: '',
  });

  const [sandboxConfig, setSandboxConfig] = useState({
    stack_level: 'minimal',
    access_methods: [] as string[],
    aap_integration: 'none',
    storage_size: '20Gi',
  });

  useEffect(() => {
    Promise.all([api.listCatalog(), api.listTenants(), api.listBrandingProfiles()]).then(
      ([cats, tens, brands]) => {
        setCatalogs(cats);
        setTenants(tens);
        setBrandings(brands);
        setLoading(false);

        const selected = cats.find((c) => c.catalog_item_id === form.catalog_item_id);
        if (selected && !form.hardware_profile) {
          setForm((f) => ({
            ...f,
            hardware_profile: selected.default_hardware_profile || '',
            ttl: selected.default_ttl || '4h',
            quota_profile: selected.default_quota_profile || 'standard',
          }));
        }
      }
    );
  }, []);

  const selectedCatalog = catalogs.find((c) => c.catalog_item_id === form.catalog_item_id);
  const isSandbox = selectedCatalog?.category === 'open_sandbox';

  const primaryColor = brandingProfile?.primary_color || '#EE0000';
  const primaryHoverColor = primaryColor === '#EE0000' ? '#A30000' : primaryColor;

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
      const requestData: Record<string, unknown> = {
        ...form,
        requested_mode: selectedCatalog?.category || 'quick_start',
      };

      if (isSandbox) {
        requestData.metadata = {
          sandbox_config: sandboxConfig,
        };
      }

      const request = await api.createLabRequest(requestData);

      if (request.status === 'rejected') {
        setError('Request was rejected. Check catalog item and tenant.');
        setSubmitting(false);
        return;
      }

      const session = await api.provisionLab(request.request_id);
      const validated = await api.validateSession(session.session_id);
      navigate(`/sessions/${validated.session_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create lab');
      setSubmitting(false);
    }
  };

  if (loading) return <div className="max-w-2xl mx-auto px-4 py-10 text-[#6A6E73]">Loading...</div>;

  return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      <h1 className="text-3xl font-bold text-[#151515] mb-2">Request a Lab</h1>
      <p className="text-[#6A6E73] mb-8">Configure and launch a new lab environment.</p>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-[#3C3F42] mb-1">Catalog Item</label>
          <select
            value={form.catalog_item_id}
            onChange={(e) => {
              const item = catalogs.find((c) => c.catalog_item_id === e.target.value);
              setForm({
                ...form,
                catalog_item_id: e.target.value,
                hardware_profile: item?.default_hardware_profile || form.hardware_profile,
                ttl: item?.default_ttl || form.ttl,
              });
            }}
            className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
            required
          >
            <option value="">Select a catalog item...</option>
            {catalogs.map((c) => (
              <option key={c.catalog_item_id} value={c.catalog_item_id}>
                {c.display_name} ({c.category.replace('_', ' ')})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-[#3C3F42] mb-1">Tenant</label>
          <select
            value={form.tenant_id}
            onChange={(e) => setForm({ ...form, tenant_id: e.target.value })}
            className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
            required
          >
            <option value="">Select a tenant...</option>
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.display_name}
              </option>
            ))}
            <option value="partner-oem-a">Partner OEM A</option>
            <option value="redhat-internal">Red Hat Internal</option>
            <option value="intel-internal">Intel Internal</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-[#3C3F42] mb-1">Requester ID</label>
          <input
            type="text"
            value={form.requester_id}
            onChange={(e) => setForm({ ...form, requester_id: e.target.value })}
            placeholder="e.g., demo-engineer-1"
            className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
            required
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-[#3C3F42] mb-1">Persistence</label>
            <select
              value={form.persistence}
              onChange={(e) => setForm({ ...form, persistence: e.target.value as 'ephemeral' | 'persistent' })}
              className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
            >
              <option value="ephemeral">Ephemeral</option>
              <option value="persistent">Persistent</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-[#3C3F42] mb-1">TTL</label>
            <select
              value={form.ttl}
              onChange={(e) => setForm({ ...form, ttl: e.target.value })}
              className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
            >
              <option value="2h">2 hours</option>
              <option value="4h">4 hours</option>
              <option value="8h">8 hours</option>
              <option value="12h">12 hours</option>
              <option value="24h">24 hours</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-[#3C3F42] mb-1">Hardware Profile</label>
            <select
              value={form.hardware_profile}
              onChange={(e) => setForm({ ...form, hardware_profile: e.target.value })}
              className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
            >
              <option value="xeon-basic">Xeon Basic</option>
              <option value="gaudi-endpoint">Gaudi Endpoint</option>
              <option value="gaudi-direct">Gaudi Direct</option>
              <option value="mixed-overdrive">Mixed Overdrive</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-[#3C3F42] mb-1">Quota Profile</label>
            <select
              value={form.quota_profile}
              onChange={(e) => setForm({ ...form, quota_profile: e.target.value })}
              className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
            >
              <option value="small">Small</option>
              <option value="standard">Standard</option>
              <option value="large">Large</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-[#3C3F42] mb-1">Branding Profile</label>
          <select
            value={form.branding_profile_id}
            onChange={(e) => setForm({ ...form, branding_profile_id: e.target.value })}
            className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
          >
            <option value="">Default</option>
            {brandings.map((b) => (
              <option key={b.branding_profile_id} value={b.branding_profile_id}>
                {b.display_name}
              </option>
            ))}
          </select>
        </div>

        {/* Sandbox Configuration - only shown for open_sandbox catalog items */}
        {isSandbox && (
          <div className="border-t border-[#D2D2D2] pt-6 mt-6">
            <h2 className="text-lg font-semibold text-[#151515] mb-1">Sandbox Configuration</h2>
            <p className="text-sm text-[#6A6E73] mb-5">Configure your open sandbox environment settings.</p>

            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-[#3C3F42] mb-1">Stack Level</label>
                <select
                  value={sandboxConfig.stack_level}
                  onChange={(e) => setSandboxConfig({ ...sandboxConfig, stack_level: e.target.value })}
                  className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
                >
                  <option value="minimal">Minimal</option>
                  <option value="ai_developer">AI Developer</option>
                  <option value="full_redhat_ai">Full Red Hat AI</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-[#3C3F42] mb-2">Access Methods</label>
                <div className="flex flex-wrap gap-3">
                  {[
                    { value: 'web_console', label: 'Web Console' },
                    { value: 'ssh', label: 'SSH' },
                    { value: 'vscode', label: 'VS Code Server' },
                    { value: 'jupyter', label: 'Jupyter' },
                    { value: 'api', label: 'API' },
                  ].map((method) => (
                    <label
                      key={method.value}
                      className={`flex items-center gap-2 px-3 py-2 rounded-md border text-sm cursor-pointer transition-colors ${
                        sandboxConfig.access_methods.includes(method.value)
                          ? 'border-[#0068B5] bg-[#0068B5]/5 text-[#0068B5]'
                          : 'border-[#D2D2D2] text-[#3C3F42] hover:border-[#6A6E73]'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={sandboxConfig.access_methods.includes(method.value)}
                        onChange={() => handleAccessMethodToggle(method.value)}
                        className="sr-only"
                      />
                      <span
                        className={`w-4 h-4 rounded border flex items-center justify-center text-xs ${
                          sandboxConfig.access_methods.includes(method.value)
                            ? 'bg-[#0068B5] border-[#0068B5] text-white'
                            : 'border-[#D2D2D2]'
                        }`}
                      >
                        {sandboxConfig.access_methods.includes(method.value) && (
                          <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                            <path d="M1 4L3.5 6.5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </span>
                      {method.label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#3C3F42] mb-1">AAP Integration</label>
                  <select
                    value={sandboxConfig.aap_integration}
                    onChange={(e) => setSandboxConfig({ ...sandboxConfig, aap_integration: e.target.value })}
                    className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
                  >
                    <option value="none">None</option>
                    <option value="playbook_library">Playbook Library</option>
                    <option value="full_aap">Full AAP</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#3C3F42] mb-1">Storage Size</label>
                  <select
                    value={sandboxConfig.storage_size}
                    onChange={(e) => setSandboxConfig({ ...sandboxConfig, storage_size: e.target.value })}
                    className="w-full border border-[#D2D2D2] rounded-md px-3 py-2 text-sm"
                  >
                    <option value="20Gi">20Gi</option>
                    <option value="50Gi">50Gi</option>
                    <option value="200Gi">200Gi</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          style={{ backgroundColor: primaryColor }}
          className="w-full py-3 text-white rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          onMouseEnter={(e) => { if (!submitting) (e.target as HTMLButtonElement).style.backgroundColor = primaryHoverColor; }}
          onMouseLeave={(e) => { if (!submitting) (e.target as HTMLButtonElement).style.backgroundColor = primaryColor; }}
        >
          {submitting ? 'Provisioning...' : isSandbox ? 'Launch Sandbox' : 'Launch Lab'}
        </button>
      </form>
    </div>
  );
}
