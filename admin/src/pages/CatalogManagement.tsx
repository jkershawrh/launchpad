import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { CatalogItem } from '../api/types';
import StatusBadge from '../components/StatusBadge';

const CATEGORIES = ['quick_start', 'guided_build', 'open_sandbox'] as const;
const HARDWARE_PROFILES = ['xeon-basic', 'gaudi-endpoint', 'gaudi-direct', 'mixed-overdrive'] as const;
const QUOTA_PROFILES = ['small', 'standard', 'large'] as const;
const TTL_OPTIONS = ['4h', '8h', '12h', '24h'] as const;

const STATUS_CYCLE: Record<string, string> = {
  draft: 'active',
  active: 'deprecated',
  deprecated: 'draft',
};

interface AddForm {
  catalog_item_id: string;
  display_name: string;
  description: string;
  category: (typeof CATEGORIES)[number];
  default_hardware_profile: string;
  default_quota_profile: string;
  default_ttl: string;
  demo_source: string;
}

const EMPTY_FORM: AddForm = {
  catalog_item_id: '',
  display_name: '',
  description: '',
  category: 'quick_start',
  default_hardware_profile: 'small',
  default_quota_profile: 'default',
  default_ttl: 'PT2H',
  demo_source: '',
};

export default function CatalogManagement() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [form, setForm] = useState<AddForm>({ ...EMPTY_FORM });
  const [submitting, setSubmitting] = useState(false);
  const [togglingStatus, setTogglingStatus] = useState<string | null>(null);

  const fetchCatalog = async () => {
    try {
      const data = await api.listCatalog();
      setItems(data);
    } catch {
      // keep existing data
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCatalog();
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.addCatalogItem({
        catalog_item_id: form.catalog_item_id,
        display_name: form.display_name,
        description: form.description,
        category: form.category,
        default_hardware_profile: form.default_hardware_profile,
        default_quota_profile: form.default_quota_profile,
        default_ttl: form.default_ttl,
      });
      setForm({ ...EMPTY_FORM });
      setShowAddForm(false);
      await fetchCatalog();
    } catch (err) {
      alert(`Failed to add catalog item: ${err}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleStatus = async (item: CatalogItem) => {
    const nextStatus = STATUS_CYCLE[item.status] || 'draft';
    if (!window.confirm(`Change status of "${item.display_name}" from "${item.status}" to "${nextStatus}"?`)) return;
    setTogglingStatus(item.catalog_item_id);
    try {
      await api.setCatalogStatus(item.catalog_item_id, nextStatus);
      await fetchCatalog();
    } catch (err) {
      alert(`Failed to update status: ${err}`);
    } finally {
      setTogglingStatus(null);
    }
  };

  const updateField = <K extends keyof AddForm>(field: K, value: AddForm[K]) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  if (loading) return <div className="max-w-6xl mx-auto px-6 py-10 text-[#6A6E73]">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-3xl font-bold text-[#151515]">Catalog</h1>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="px-4 py-2 text-sm font-medium rounded bg-[#EE0000] text-white hover:bg-[#CC0000] transition-colors"
        >
          {showAddForm ? 'Cancel' : 'Add Demo'}
        </button>
      </div>
      <p className="text-[#6A6E73] mb-8">Manage catalog items and demo configurations.</p>

      {/* Add form */}
      {showAddForm && (
        <form onSubmit={handleAdd} className="bg-white rounded border border-[#D2D2D2] p-6 mb-8">
          <h2 className="text-sm font-semibold text-[#6A6E73] uppercase mb-4">New Catalog Item</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-[#151515] mb-1">Catalog Item ID</label>
              <input
                type="text"
                required
                value={form.catalog_item_id}
                onChange={(e) => updateField('catalog_item_id', e.target.value)}
                placeholder="e.g. rag-chatbot-v1"
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#0068B5]"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#151515] mb-1">Display Name</label>
              <input
                type="text"
                required
                value={form.display_name}
                onChange={(e) => updateField('display_name', e.target.value)}
                placeholder="e.g. RAG Chatbot"
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#0068B5]"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-[#151515] mb-1">Description</label>
              <textarea
                required
                value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
                placeholder="Brief description of the demo..."
                rows={2}
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#0068B5]"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#151515] mb-1">Category</label>
              <select
                value={form.category}
                onChange={(e) => updateField('category', e.target.value as AddForm['category'])}
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#0068B5]"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-[#151515] mb-1">Hardware Profile</label>
              <select
                value={form.default_hardware_profile}
                onChange={(e) => updateField('default_hardware_profile', e.target.value)}
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#0068B5]"
              >
                {HARDWARE_PROFILES.map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-[#151515] mb-1">Quota Profile</label>
              <select
                value={form.default_quota_profile}
                onChange={(e) => updateField('default_quota_profile', e.target.value)}
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#0068B5]"
              >
                {QUOTA_PROFILES.map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-[#151515] mb-1">Default TTL</label>
              <select
                value={form.default_ttl}
                onChange={(e) => updateField('default_ttl', e.target.value)}
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#0068B5]"
              >
                {TTL_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-[#151515] mb-1">Demo Source (metadata)</label>
              <input
                type="text"
                value={form.demo_source}
                onChange={(e) => updateField('demo_source', e.target.value)}
                placeholder="e.g. https://github.com/org/repo"
                className="w-full border border-[#D2D2D2] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#0068B5]"
              />
            </div>
          </div>
          <div className="mt-4 flex justify-end">
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium rounded bg-[#0068B5] text-white hover:bg-[#005A9E] transition-colors disabled:opacity-50"
            >
              {submitting ? 'Adding...' : 'Add Catalog Item'}
            </button>
          </div>
        </form>
      )}

      {/* Table */}
      {items.length === 0 ? (
        <div className="bg-white rounded border border-[#D2D2D2] p-8 text-center text-[#6A6E73]">
          No catalog items found.
        </div>
      ) : (
        <div className="bg-white rounded border border-[#D2D2D2] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[#6A6E73] text-xs uppercase bg-[#F0F0F0] border-b border-[#D2D2D2]">
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Name</th>
                <th className="py-3 px-4">Category</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Hardware</th>
                <th className="py-3 px-4">TTL</th>
                <th className="py-3 px-4">Provisioner</th>
                <th className="py-3 px-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.catalog_item_id} className="border-b border-[#F0F0F0] last:border-0 hover:bg-[#F0F0F0]/50">
                  <td className="py-3 px-4 font-mono text-xs text-[#151515]">{item.catalog_item_id}</td>
                  <td className="py-3 px-4 text-[#151515]">
                    <span>{item.display_name}</span>
                    {(item.metadata as Record<string, unknown>)?.official_quickstart && (
                      <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold bg-[#EE0000] text-white uppercase">Official</span>
                    )}
                  </td>
                  <td className="py-3 px-4"><StatusBadge status={item.category} /></td>
                  <td className="py-3 px-4"><StatusBadge status={item.status} /></td>
                  <td className="py-3 px-4 text-xs text-[#6A6E73]">{item.default_hardware_profile || '—'}</td>
                  <td className="py-3 px-4 text-xs text-[#6A6E73]">{item.default_ttl || '—'}</td>
                  <td className="py-3 px-4">
                    {(item.metadata as Record<string, unknown>)?.provisioner_mode === 'rhdp' ? (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-medium">RHDP</span>
                    ) : (
                      <span className="text-xs text-[#6A6E73]">Direct</span>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleToggleStatus(item)}
                        disabled={togglingStatus === item.catalog_item_id}
                        className="px-2 py-1 text-xs font-medium rounded border border-[#0068B5] text-[#0068B5] hover:bg-[#0068B5] hover:text-white transition-colors disabled:opacity-50"
                      >
                        {togglingStatus === item.catalog_item_id ? 'Updating...' : `Set ${STATUS_CYCLE[item.status] || 'draft'}`}
                      </button>
                      <button
                        disabled
                        title="Coming soon"
                        className="px-2 py-1 text-xs font-medium rounded border border-[#D2D2D2] text-[#6A6E73] cursor-not-allowed opacity-50"
                      >
                        Edit
                      </button>
                    </div>
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
