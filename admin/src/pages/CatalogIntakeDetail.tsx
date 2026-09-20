import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { CatalogIntakeDraft, CatalogIntakePipelineView } from '../api/types';
import IntakeStageBadge from '../components/IntakeStageBadge';

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="rounded border border-[#333] bg-[#212121] p-5 sm:p-6"><h2 className="text-lg font-semibold text-white">{title}</h2><div className="mt-4">{children}</div></section>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded border border-dashed border-[#555] bg-[#1A1A1A] p-4 text-sm text-[#A3A3A3]">{children}</p>;
}

export default function CatalogIntakeDetail() {
  const { intakeId = '' } = useParams();
  const [draft, setDraft] = useState<CatalogIntakeDraft | null>(null);
  const [pipeline, setPipeline] = useState<CatalogIntakePipelineView | null>(null);
  const [error, setError] = useState('');
  const [mutating, setMutating] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([api.getCatalogIntake(intakeId), api.getCatalogIntakePipeline(intakeId)])
      .then(([item, pipelineView]) => { if (active) { setDraft(item); setPipeline(pipelineView); } })
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : 'Unable to load intake'));
    return () => { active = false; };
  }, [intakeId]);

  if (error) return <div className="mx-auto max-w-5xl px-6 py-10"><p role="alert" className="rounded border border-[#C9190B] bg-[#2B1717] p-4 text-[#FF8D85]">Unable to load intake: {error}</p></div>;
  if (!draft) return <div role="status" className="mx-auto max-w-5xl px-6 py-10 text-[#A3A3A3]">Loading intake…</div>;

  const revision = draft.release_identity.revision;
  const mutate = async (action: 'approve' | 'discover') => {
    setError(''); setMutating(true);
    try {
      const updated = action === 'approve' ? await api.approveCatalogIntakeSource(intakeId) : await api.runCatalogIntakeDiscovery(intakeId);
      setDraft(updated);
      setPipeline(await api.getCatalogIntakePipeline(intakeId));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Intake action failed'); }
    finally { setMutating(false); }
  };
  return <div className="mx-auto max-w-7xl px-6 py-10 lg:px-8">
    <Link to="/intakes" className="text-sm font-semibold text-[#58A6E7] hover:underline">← Back to intake</Link>
    <header className="mt-5 flex flex-col justify-between gap-5 border-b border-[#333] pb-7 lg:flex-row lg:items-start"><div><div className="mb-3 flex flex-wrap items-center gap-3"><IntakeStageBadge state={draft.state} /><span className="rounded-full border border-[#555] px-2.5 py-1 text-xs text-[#A3A3A3]">Stage: {draft.catalog_preview ? 'Catalog draft review' : 'Intake draft'}</span><span className="rounded-full border border-[#555] px-2.5 py-1 text-xs text-[#A3A3A3]">Not orderable</span></div><h1 className="text-3xl font-bold text-white">{draft.requested.display_name}</h1><p className="mt-2 font-mono text-sm text-[#A3A3A3]">{draft.intake_id}</p></div><div className="flex flex-wrap gap-3">{pipeline?.actions.approve_source && <button type="button" disabled={mutating} onClick={() => void mutate('approve')} className="rounded border border-[#58A6E7] px-4 py-2 text-sm font-semibold text-[#B8DAF4] disabled:opacity-50">Approve source</button>}{pipeline?.actions.run_discovery && <button type="button" disabled={mutating} onClick={() => void mutate('discover')} className="rounded bg-[#0068B5] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Run discovery</button>}<button type="button" disabled aria-describedby="actions-help" title="Evidence and approval gates are incomplete" className="rounded border border-[#555] px-4 py-2 text-sm font-semibold text-[#6A6E73] disabled:cursor-not-allowed">Run certification</button><button type="button" disabled aria-describedby="actions-help" title="This draft is not promotion eligible" className="rounded bg-[#555] px-4 py-2 text-sm font-semibold text-[#A3A3A3] disabled:cursor-not-allowed">Promote to catalog</button></div><p id="actions-help" className="sr-only">Certification and promotion remain disabled until the required evidence, target, approval, and rollback gates exist.</p></header>

    <div className="mt-7 grid gap-6 lg:grid-cols-3"><div className="space-y-6 lg:col-span-2">
      <Panel title="Canonical Quickstart source"><p className="mb-4 text-sm text-[#A3A3A3]">Launchpad discovers source metadata from this pinned Quickstart. Requested fields are draft hints or explicit Launchpad overrides.</p><dl className="grid gap-4 text-sm sm:grid-cols-2"><div className="sm:col-span-2"><dt className="text-[#A3A3A3]">Repository</dt><dd className="mt-1 break-all text-white"><a className="text-[#58A6E7] hover:underline" href={draft.release_identity.repository_url} target="_blank" rel="noreferrer">{draft.release_identity.repository_url}</a></dd></div><div className="sm:col-span-2"><dt className="text-[#A3A3A3]">Immutable revision</dt><dd className="mt-1 break-all rounded bg-[#151515] p-3 font-mono text-xs text-white">{revision}</dd></div><div><dt className="text-[#A3A3A3]">Owner hint</dt><dd className="mt-1 text-white">{draft.requested.owner}</dd></div><div><dt className="text-[#A3A3A3]">Lab type hint</dt><dd className="mt-1 text-white">{draft.requested.lab_type.replaceAll('_', ' ')}</dd></div><div><dt className="text-[#A3A3A3]">Expected scale hint</dt><dd className="mt-1 text-white">{draft.requested.expected_scale} seats</dd></div><div><dt className="text-[#A3A3A3]">Current certified ceiling</dt><dd className="mt-1 font-semibold text-[#F8C95E]">{draft.defaults.maximum_seats} {draft.defaults.maximum_seats === 1 ? 'seat' : 'seats'}</dd></div></dl></Panel>
      {draft.discovery && <Panel title="Discovery result"><div className="flex flex-wrap items-center gap-3"><span className="rounded-full bg-[#153C2D] px-2.5 py-1 text-xs font-semibold text-[#7CE2B2]">Passed</span><span className="text-sm text-[#D2D2D2]">{draft.discovery.files_scanned} files scanned</span><span className="text-sm text-[#D2D2D2]">{draft.discovery.bytes_scanned.toLocaleString()} bytes</span></div><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2"><div><dt className="text-[#A3A3A3]">Attempt</dt><dd className="mt-1 font-mono text-xs text-white">{draft.discovery.attempt_id}</dd></div><div><dt className="text-[#A3A3A3]">Cleanup</dt><dd className="mt-1 text-[#7CE2B2]">Verified</dd></div><div className="sm:col-span-2"><dt className="text-[#A3A3A3]">Sanitized output hash</dt><dd className="mt-1 break-all font-mono text-xs text-white">{draft.discovery.output_hash}</dd></div></dl></Panel>}
      {draft.discovery_execution && <Panel title="Discovery execution"><p className="text-sm text-white">{draft.discovery_execution.state}</p>{draft.discovery_execution.error_codes.length > 0 && <p className="mt-2 text-sm text-[#FF8D85]">{draft.discovery_execution.error_codes.join(', ')}</p>}</Panel>}
      {draft.catalog_preview && <Panel title="Catalog draft preview"><p className="text-sm text-[#A3A3A3]">Generated deterministically from the pinned Quickstart. This preview is internal, non-orderable, and cannot be published yet.</p><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2"><div><dt className="text-[#A3A3A3]">Catalog ID</dt><dd className="mt-1 font-mono text-white">{draft.catalog_preview.catalog_item_id}</dd></div><div><dt className="text-[#A3A3A3]">Version</dt><dd className="mt-1 text-white">{draft.catalog_preview.version}</dd></div><div><dt className="text-[#A3A3A3]">Category</dt><dd className="mt-1 text-white">{draft.catalog_preview.category.replaceAll('_', ' ')}</dd></div><div><dt className="text-[#A3A3A3]">Status</dt><dd className="mt-1 text-[#F8C95E]">Draft</dd></div><div className="sm:col-span-2"><dt className="text-[#A3A3A3]">Required capabilities</dt><dd className="mt-1 text-white">{draft.catalog_preview.required_capabilities.length ? draft.catalog_preview.required_capabilities.join(', ') : 'None discovered'}</dd></div></dl></Panel>}
      <Panel title="Blockers"><p className="mb-4 text-sm text-[#A3A3A3]">All blockers must be resolved through evidence-backed gates before promotion becomes available.</p>{draft.blockers.length ? <ul className="space-y-2">{draft.blockers.map((blocker) => <li key={blocker} className="flex gap-3 rounded border border-[#F0AB00]/30 bg-[#2B2414] p-3 text-sm text-[#F8C95E]"><span aria-hidden="true">◆</span><span>{blocker}</span></li>)}</ul> : <Empty>No blockers recorded</Empty>}</Panel>
      <Panel title="Intake path">{pipeline ? <><p className="text-sm text-[#A3A3A3]">Current stage: <strong className="text-white">{pipeline.current_stage}</strong> · metadata policy: <strong className="text-white">discover from source</strong></p><ol className="mt-4 grid gap-3 sm:grid-cols-2">{pipeline.stages.map((stage) => <li key={stage.stage_id} className={`rounded border p-3 ${stage.status === 'current' ? 'border-[#58A6E7] bg-[#172638]' : 'border-[#333] bg-[#1A1A1A]'}`}><div className="flex items-center justify-between gap-2"><strong className="text-sm text-white">{stage.label}</strong><span className="text-xs uppercase text-[#A3A3A3]">{stage.status}</span></div><p className="mt-2 text-xs text-[#A3A3A3]">{stage.gate_ids.length} gate{stage.gate_ids.length === 1 ? '' : 's'}</p></li>)}</ol></> : <Empty>Pipeline contract unavailable</Empty>}</Panel>
      <Panel title="Evidence"><div className="flex flex-wrap items-center gap-3"><span className="rounded-full bg-[#2B2414] px-2.5 py-1 text-xs font-semibold text-[#F8C95E]">{draft.evidence.status}</span><span className="text-sm text-[#A3A3A3]">{draft.evidence.artifacts.length} artifacts attached</span></div><h3 className="mt-5 text-sm font-semibold text-white">Required gates</h3>{draft.evidence.required_gates.length ? <ul className="mt-3 grid gap-2 sm:grid-cols-2">{draft.evidence.required_gates.map((gate) => <li key={gate} className="rounded border border-[#333] bg-[#1A1A1A] px-3 py-2 text-sm text-[#D2D2D2]">{gate}</li>)}</ul> : <Empty>No evidence gates declared</Empty>}</Panel>
    </div><aside className="space-y-6">
      <Panel title="Supported targets">{draft.supported_targets.length ? <ul className="space-y-2">{draft.supported_targets.map((target) => <li key={target} className="rounded bg-[#1A1A1A] px-3 py-2 text-sm text-white">{target}</li>)}</ul> : <Empty>No targets verified</Empty>}<p className="mt-3 text-xs text-[#A3A3A3]">Target status: {draft.target_status}</p></Panel>
      <Panel title="Approvals">{draft.approval_history.length ? <ul>{draft.approval_history.map((approval, index) => <li key={`${index}-${JSON.stringify(approval)}`} className="text-sm text-white">{Object.values(approval).join(' · ')}</li>)}</ul> : <Empty>No approvals recorded</Empty>}</Panel>
      <Panel title="Rollback">{draft.rollback.status === 'not-defined' ? <Empty>Rollback not defined</Empty> : <p className="text-sm text-white">{draft.rollback.status}</p>}</Panel>
      <Panel title="Draft boundary"><dl className="space-y-3 text-sm"><div><dt className="text-[#A3A3A3]">Storage</dt><dd className="mt-1 text-white">{draft.storage_scope === 'durable-postgres' ? 'Durable PostgreSQL' : 'Process-local draft'}</dd></div><div><dt className="text-[#A3A3A3]">Exposure</dt><dd className="mt-1 text-white">{draft.defaults.exposure_policies.join(', ')}</dd></div><div><dt className="text-[#A3A3A3]">Promotion eligible</dt><dd className="mt-1 text-[#FF8D85]">No</dd></div></dl></Panel>
    </aside></div>
  </div>;
}
