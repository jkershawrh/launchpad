import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogIntakeLabType, CatalogIntakeSubmission } from '../api/types';

const initial: CatalogIntakeSubmission = { catalog_item_id: '', display_name: '', repository_url: '', revision: '', owner: '', audience: [], duration_hours: 4, lab_type: 'guided_build', expected_scale: 25 };

export default function NewCatalogIntake() {
  const [form, setForm] = useState(initial);
  const [audience, setAudience] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();
  const field = <K extends keyof CatalogIntakeSubmission>(key: K, value: CatalogIntakeSubmission[K]) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(''); setSubmitting(true);
    try {
      const draft = await api.submitCatalogIntake({ ...form, audience: audience.split(',').map((item) => item.trim()).filter(Boolean) });
      navigate(`/intakes/${encodeURIComponent(draft.intake_id)}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Submission failed'); }
    finally { setSubmitting(false); }
  };

  const inputClass = 'mt-1 w-full rounded border border-[#555] bg-[#151515] px-3 py-2.5 text-sm text-white focus:border-[#58A6E7] focus:outline-none focus:ring-1 focus:ring-[#58A6E7]';
  return <div className="mx-auto max-w-4xl px-6 py-10 lg:px-8"><Link to="/intakes" className="text-sm font-semibold text-[#58A6E7] hover:underline">← Back to intake</Link><div className="mt-5"><p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#58A6E7]">New draft</p><h1 className="text-3xl font-bold text-white">Submit a Quickstart repository</h1><p className="mt-2 text-sm text-[#A3A3A3]">This creates a non-orderable draft. It does not certify, approve, or promote a lab.</p></div>
    {error && <p role="alert" className="mt-6 rounded border border-[#C9190B] bg-[#2B1717] p-4 text-sm text-[#FF8D85]">{error}</p>}
    <form onSubmit={submit} className="mt-8 space-y-7 rounded border border-[#333] bg-[#212121] p-6 sm:p-8"><div className="rounded border border-[#0068B5]/50 bg-[#172638] p-4 text-sm text-[#B8DAF4]"><strong className="text-white">Repo-first intake.</strong> The pinned Quickstart is the canonical source of lab metadata. Launchpad discovery will read that source; the hints below do not replace or duplicate its configuration.</div><fieldset><legend className="text-lg font-semibold text-white">1. Quickstart source</legend><p className="mt-1 text-sm text-[#A3A3A3]">Pin the exact repository state Launchpad should inspect.</p><div className="mt-4 grid gap-5"><label className="text-sm text-[#D2D2D2]">HTTPS GitHub repository<input required type="url" value={form.repository_url} onChange={(e) => field('repository_url', e.target.value)} className={inputClass} placeholder="https://github.com/org/repository" /></label><label className="text-sm text-[#D2D2D2]">Immutable Git SHA<input required minLength={40} maxLength={40} pattern="[0-9a-f]{40}" value={form.revision} onChange={(e) => field('revision', e.target.value)} className={`${inputClass} font-mono`} aria-describedby="revision-help" /><span id="revision-help" className="mt-1 block text-xs text-[#A3A3A3]">Exactly 40 lowercase hexadecimal characters; branches and tags are not accepted.</span></label></div></fieldset>
      <fieldset><legend className="text-lg font-semibold text-white">2. Launchpad draft hints</legend><p className="mt-1 text-sm text-[#A3A3A3]">Required by the current intake contract and reconciled with discovered Quickstart metadata. Treat these as initial Launchpad hints or intentional overrides—not a second lab definition.</p><div className="mt-4 grid gap-5 sm:grid-cols-2"><label className="text-sm text-[#D2D2D2]">Catalog item ID<input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" value={form.catalog_item_id} onChange={(e) => field('catalog_item_id', e.target.value)} className={inputClass} placeholder="agent-lab" /></label><label className="text-sm text-[#D2D2D2]">Display name<input required value={form.display_name} onChange={(e) => field('display_name', e.target.value)} className={inputClass} /></label><label className="text-sm text-[#D2D2D2]">Owner<input required value={form.owner} onChange={(e) => field('owner', e.target.value)} className={inputClass} /></label><label className="text-sm text-[#D2D2D2]">Audience<input required value={audience} onChange={(e) => setAudience(e.target.value)} className={inputClass} placeholder="solution architects, partners" /><span className="mt-1 block text-xs text-[#A3A3A3]">Separate multiple audiences with commas.</span></label><label className="text-sm text-[#D2D2D2]">Lab type<select value={form.lab_type} onChange={(e) => field('lab_type', e.target.value as CatalogIntakeLabType)} className={inputClass}><option value="quick_start">Quick start</option><option value="guided_build">Guided build</option><option value="open_sandbox">Open sandbox</option></select></label><label className="text-sm text-[#D2D2D2]">Duration (hours)<input required type="number" min={1} max={168} value={form.duration_hours} onChange={(e) => field('duration_hours', Number(e.target.value))} className={inputClass} /></label><label className="text-sm text-[#D2D2D2]">Expected seat scale<input required type="number" min={1} max={1000} value={form.expected_scale} onChange={(e) => field('expected_scale', Number(e.target.value))} className={inputClass} /></label></div></fieldset>
      <div className="flex flex-col-reverse gap-3 border-t border-[#333] pt-6 sm:flex-row sm:justify-end"><Link to="/intakes" className="inline-flex min-h-10 items-center justify-center rounded border border-[#555] px-4 py-2 text-sm font-semibold text-white hover:bg-white/5">Cancel</Link><button disabled={submitting} className="min-h-10 rounded bg-[#EE0000] px-5 py-2 text-sm font-semibold text-white hover:bg-[#CC0000] disabled:cursor-not-allowed disabled:opacity-50">{submitting ? 'Submitting…' : 'Create intake draft'}</button></div></form></div>;
}
