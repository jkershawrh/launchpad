import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { CatalogItem, Tenant, Workshop, WorkshopCapacityPreview } from '../api/types';
import { validateSeatCount } from '../workshopOrderContract';

export default function WorkshopOrderForm() {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [preview, setPreview] = useState<WorkshopCapacityPreview | null>(null);
  const [workshop, setWorkshop] = useState<Workshop | null>(null);
  const [idempotencyKey] = useState(() => `workshop-${crypto.randomUUID()}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    name: '', owner_id: '', tenant_id: '', catalog_item_id: 'guided-rag-on-xeon', num_users: 20, ttl: '4h',
  });

  useEffect(() => {
    Promise.all([api.listCatalog(), api.listTenants()]).then(([items, tenantItems]) => {
      setCatalog(items.filter((item) => item.category !== 'open_sandbox'));
      setTenants(tenantItems.filter((tenant) => tenant.status === 'active'));
    });
  }, []);

  const seatError = validateSeatCount(form.num_users);
  const checkCapacity = async () => {
    if (seatError) return setError(seatError);
    setBusy(true); setError(''); setWorkshop(null);
    try { setPreview(await api.previewWorkshop(form)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Capacity check failed'); }
    finally { setBusy(false); }
  };

  const orderWorkshop = async () => {
    setBusy(true); setError('');
    try {
      setWorkshop(await api.createWorkshopOrder(form, idempotencyKey));
    } catch (err) { setError(err instanceof Error ? err.message : 'Order failed'); }
    finally { setBusy(false); }
  };

  const confirm = async () => {
    if (!workshop) return;
    setBusy(true);
    try { setWorkshop(await api.confirmWorkshop(workshop.workshop_id)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Confirmation failed'); }
    finally { setBusy(false); }
  };

  const field = 'w-full rounded-md border border-[#D2D2D2] px-3 py-2 text-sm';
  return <div className="mx-auto max-w-3xl px-4 py-10">
    <h1 className="mb-2 text-3xl font-bold text-[#151515]">Create Workshop</h1>
    <p className="mb-8 text-[#6A6E73]">Order one personalized lab environment and Showroom guide per participant.</p>
    {error && <div className="mb-5 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    <div className="grid gap-5 rounded-lg border border-[#D2D2D2] bg-white p-6 md:grid-cols-2">
      <label className="text-sm font-medium">Workshop name<input className={`${field} mt-1`} value={form.name} onChange={(e) => setForm({...form, name:e.target.value})} /></label>
      <label className="text-sm font-medium">Instructor ID<input required className={`${field} mt-1`} value={form.owner_id} onChange={(e) => setForm({...form, owner_id:e.target.value})} /></label>
      <label className="text-sm font-medium">Tenant<select required className={`${field} mt-1`} value={form.tenant_id} onChange={(e) => setForm({...form, tenant_id:e.target.value})}><option value="">Select tenant…</option>{tenants.map((t)=><option key={t.tenant_id} value={t.tenant_id}>{t.display_name}</option>)}</select></label>
      <label className="text-sm font-medium">Lab<select className={`${field} mt-1`} value={form.catalog_item_id} onChange={(e) => setForm({...form, catalog_item_id:e.target.value})}>{catalog.map((c)=><option key={c.catalog_item_id} value={c.catalog_item_id}>{c.display_name}</option>)}</select></label>
      <label className="text-sm font-medium">Seat count<input type="number" min="1" max="100" className={`${field} mt-1`} value={form.num_users} onChange={(e) => setForm({...form, num_users:Number(e.target.value)})} /></label>
      <label className="text-sm font-medium">Duration<select className={`${field} mt-1`} value={form.ttl} onChange={(e) => setForm({...form, ttl:e.target.value})}><option value="4h">4 hours</option><option value="8h">8 hours</option><option value="1d">1 day</option></select></label>
    </div>
    <button disabled={busy || !form.tenant_id || !form.owner_id || !!seatError} onClick={checkCapacity} className="mt-6 rounded bg-[#0068B5] px-5 py-2.5 font-semibold text-white disabled:opacity-50">{busy ? 'Checking…' : 'Check capacity'}</button>
    {preview && <section className="mt-6 rounded-lg border border-[#D2D2D2] bg-white p-6">
      <h2 className="text-xl font-bold">Capacity review</h2>
      <p className="mt-2 text-sm text-[#3C3F42]">{preview.reason}</p>
      <div className="mt-4 grid grid-cols-3 gap-4 text-sm"><div><b>{preview.seats_requested}</b><br/>seats</div><div><b>{preview.estimated_resources.cpu_millicores / 1000}</b><br/>CPU cores</div><div><b>{Math.round(preview.estimated_resources.memory_mib / 1024)}</b><br/>GiB memory</div></div>
      {!workshop && <button disabled={!preview.can_provision || busy} onClick={orderWorkshop} className="mt-5 rounded bg-[#EE0000] px-5 py-2.5 font-semibold text-white disabled:opacity-50">Create order</button>}
    </section>}
    {workshop && <section className="mt-6 rounded-lg border border-[#D2D2D2] bg-white p-6"><h2 className="text-xl font-bold">Order ready for confirmation</h2><p className="mt-2 text-sm">{workshop.num_users} isolated seats · status: <b>{workshop.status.replace('_',' ')}</b></p><p className="mt-1 font-mono text-xs text-[#6A6E73]">{workshop.workshop_id}</p>{workshop.status === 'awaiting_confirmation' && <button disabled={busy} onClick={confirm} className="mt-5 rounded bg-[#EE0000] px-5 py-2.5 font-semibold text-white">Confirm and provision</button>}</section>}
  </div>;
}
