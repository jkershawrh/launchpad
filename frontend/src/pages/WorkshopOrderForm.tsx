import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogItem, Tenant, Workshop, WorkshopCapacityPreview } from '../api/types';
import { MAX_WORKSHOP_SEATS, validateSeatCount } from '../workshopOrderContract';

export default function WorkshopOrderForm({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [preview, setPreview] = useState<WorkshopCapacityPreview | null>(null);
  const [workshop, setWorkshop] = useState<Workshop | null>(null);
  const [idempotencyKey] = useState(() => `workshop-${crypto.randomUUID()}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    name: '', owner_id: '', tenant_id: '', catalog_item_id: 'openshift-operators-workshop', num_users: 25, ttl: '4h',
  });

  useEffect(() => {
    Promise.all([api.listCatalog(), api.listTenants()]).then(([items, tenantItems]) => {
      setCatalog(items.filter((item) => item.category !== 'open_sandbox' && item.status === 'active'));
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
    try {
      await api.confirmWorkshop(workshop.workshop_id);
      navigate(`/workshops/${workshop.workshop_id}`);
    }
    catch (err) { setError(err instanceof Error ? err.message : 'Confirmation failed'); }
    finally { setBusy(false); }
  };

  const field = 'mt-1 w-full rounded-md border border-[#D2D2D2] bg-[#151515] px-4 py-2.5 text-sm text-white outline-none transition focus:border-[#0071C5] focus:ring-1 focus:ring-[#0071C5]';
  const label = 'block text-sm font-medium text-[#B8BBBE]';
  return <div className={embedded ? '' : 'mx-auto max-w-2xl px-4 py-10'}>
    {!embedded && <><h1 className="mb-2 text-3xl font-bold text-white">Request an Environment</h1><p className="mb-8 text-[#8A8D90]">Configure one guided workshop with an isolated environment for every participant.</p></>}
    {error && <div className="mb-6 rounded border border-[#C9190B]/50 bg-[#C9190B]/15 px-4 py-3 text-sm text-red-200">{error}</div>}

    <div className="space-y-6">
      <label className={label}>Workshop name<input className={field} value={form.name} onChange={(e) => setForm({...form, name:e.target.value})} placeholder="e.g., Intel partner enablement" /></label>
      <label className={label}>Instructor ID<input required className={field} value={form.owner_id} onChange={(e) => setForm({...form, owner_id:e.target.value})} placeholder="e.g., instructor-1" /></label>
      <label className={label}>Tenant<select required className={field} value={form.tenant_id} onChange={(e) => setForm({...form, tenant_id:e.target.value})}><option value="">Select a tenant...</option>{tenants.map((t)=><option key={t.tenant_id} value={t.tenant_id}>{t.display_name}</option>)}</select></label>
      <label className={label}>Lab<select className={field} value={form.catalog_item_id} onChange={(e) => setForm({...form, catalog_item_id:e.target.value})}>{catalog.map((c)=><option key={c.catalog_item_id} value={c.catalog_item_id}>{c.display_name}</option>)}</select></label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={label}>Participant seats<input type="number" min="1" max={MAX_WORKSHOP_SEATS} className={field} value={form.num_users} onChange={(e) => setForm({...form, num_users:Number(e.target.value)})} /><span className="mt-1 block text-xs font-normal text-[#6A6E73]">Maximum {MAX_WORKSHOP_SEATS} seats in one workshop.</span></label>
        <label className={label}>Duration<select className={field} value={form.ttl} onChange={(e) => setForm({...form, ttl:e.target.value})}><option value="4h">4 hours</option><option value="8h">8 hours</option><option value="1d">1 day</option></select></label>
      </div>
    </div>

    <button disabled={busy || !form.tenant_id || !form.owner_id || !!seatError} onClick={checkCapacity} className="mt-6 w-full rounded-md bg-[#EE0000] px-5 py-3 font-semibold text-white transition hover:bg-[#CC0000] disabled:cursor-not-allowed disabled:opacity-40">{busy ? 'Checking capacity…' : 'Check capacity'}</button>

    {preview && <section className="mt-6 rounded-md border border-[#333] bg-[#212121] p-6">
      <div className="flex items-start justify-between gap-4"><div><h2 className="text-xl font-bold text-white">Capacity review</h2><p className="mt-2 text-sm text-[#B8BBBE]">{preview.reason}</p></div><span className={`rounded-full px-3 py-1 text-xs font-semibold ${preview.can_provision ? 'bg-[#3E8635]/20 text-green-300' : 'bg-[#C9190B]/20 text-red-300'}`}>{preview.can_provision ? 'Capacity available' : 'Unavailable'}</span></div>
      <div className="mt-5 grid grid-cols-3 gap-4 border-y border-[#333] py-4 text-sm text-[#8A8D90]"><div><b className="text-xl text-white">{preview.seats_requested}</b><br/>seats</div><div><b className="text-xl text-white">{preview.estimated_resources.cpu_millicores / 1000}</b><br/>CPU cores</div><div><b className="text-xl text-white">{Math.round(preview.estimated_resources.memory_mib / 1024)}</b><br/>GiB memory</div></div>
      {!workshop && <button disabled={!preview.can_provision || busy} onClick={orderWorkshop} className="mt-5 w-full rounded-md bg-[#EE0000] px-5 py-3 font-semibold text-white hover:bg-[#CC0000] disabled:opacity-40">Create workshop order</button>}
    </section>}

    {workshop && <section className="mt-6 rounded-md border border-[#0071C5]/60 bg-[#0071C5]/10 p-6"><h2 className="text-xl font-bold text-white">Ready for confirmation</h2><p className="mt-2 text-sm text-[#D2D2D2]">One workshop · {workshop.num_users} isolated participant seats</p><p className="mt-2 font-mono text-xs text-[#8A8D90]">{workshop.workshop_id}</p>{workshop.status === 'awaiting_confirmation' && <button disabled={busy} onClick={confirm} className="mt-5 w-full rounded-md bg-[#EE0000] px-5 py-3 font-semibold text-white hover:bg-[#CC0000] disabled:opacity-40">Confirm and start provisioning</button>}</section>}
  </div>;
}
