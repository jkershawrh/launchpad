import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Tenant } from '../api/types';
import StatusBadge from '../components/StatusBadge';

export default function Tenants() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    tenant_id: '',
    display_name: '',
    tenant_type: 'partner',
    branding_profile_id: '',
    default_quota_profile: 'standard',
    default_ttl: '8h',
  });
  const [error, setError] = useState('');

  const loadTenants = () => {
    api.listTenants().then((data) => {
      setTenants(data);
      setLoading(false);
    });
  };

  useEffect(() => { loadTenants(); }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await api.createTenant(form);
      setShowForm(false);
      setForm({ tenant_id: '', display_name: '', tenant_type: 'partner', branding_profile_id: '', default_quota_profile: 'standard', default_ttl: '8h' });
      loadTenants();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create tenant');
    }
  };

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-[#151515]">Tenants</h1>
          <p className="text-[#6A6E73] mt-1">Manage partner, client, and internal tenants.</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-[#EE0000] text-white rounded text-sm font-medium hover:bg-[#A30000] transition-colors"
        >
          {showForm ? 'Cancel' : 'Create Tenant'}
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded border border-[#D2D2D2] p-6 mb-8">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">New Tenant</h2>
          {error && <div className="bg-red-50 border border-red-200 text-[#C9190B] px-4 py-2 rounded mb-4 text-sm">{error}</div>}
          <form onSubmit={handleSubmit} className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[#3C3F42] mb-1">Tenant ID</label>
              <input type="text" value={form.tenant_id} onChange={(e) => setForm({ ...form, tenant_id: e.target.value })}
                placeholder="e.g., partner-acme" className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm" required />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#3C3F42] mb-1">Display Name</label>
              <input type="text" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                placeholder="e.g., ACME Corp" className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm" required />
            </div>
            <div>
              <label className="block text-sm font-medium text-[#3C3F42] mb-1">Type</label>
              <select value={form.tenant_type} onChange={(e) => setForm({ ...form, tenant_type: e.target.value })}
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm">
                <option value="partner">Partner</option>
                <option value="client">Client</option>
                <option value="redhat_internal">Red Hat Internal</option>
                <option value="intel_internal">Intel Internal</option>
                <option value="demo">Demo</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-[#3C3F42] mb-1">Default TTL</label>
              <select value={form.default_ttl} onChange={(e) => setForm({ ...form, default_ttl: e.target.value })}
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm">
                <option value="4h">4 hours</option>
                <option value="8h">8 hours</option>
                <option value="12h">12 hours</option>
                <option value="24h">24 hours</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <button type="submit" className="px-4 py-2 bg-[#EE0000] text-white rounded text-sm font-medium hover:bg-[#A30000]">
                Create
              </button>
            </div>
          </form>
        </div>
      )}

      {tenants.length === 0 ? (
        <div className="bg-white rounded border border-[#D2D2D2] p-8 text-center text-[#6A6E73]">
          No tenants created yet.
        </div>
      ) : (
        <div className="bg-white rounded border border-[#D2D2D2] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase bg-[#F0F0F0] border-b border-[#D2D2D2]">
                <th className="py-3 px-4">Tenant ID</th>
                <th className="py-3 px-4">Display Name</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Quota</th>
                <th className="py-3 px-4">TTL</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.tenant_id} className="border-b border-[#F0F0F0] last:border-0">
                  <td className="py-3 px-4 font-mono text-xs text-[#151515]">{t.tenant_id}</td>
                  <td className="py-3 px-4 text-[#151515] font-medium">{t.display_name}</td>
                  <td className="py-3 px-4"><StatusBadge status={t.tenant_type} /></td>
                  <td className="py-3 px-4"><StatusBadge status={t.status} /></td>
                  <td className="py-3 px-4 text-[#6A6E73]">{t.default_quota_profile || '—'}</td>
                  <td className="py-3 px-4 text-[#6A6E73]">{t.default_ttl || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
