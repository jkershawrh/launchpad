from __future__ import annotations

from app.domain.catalog_intake import CatalogIntakeDraft
from app.domain.catalog_intake_pipeline import (
    CatalogIntakePipelineGate,
    CatalogIntakePipelineStage,
    CatalogIntakePipelineView,
)

GATES = (
    ("repository-discovery", "Repository discovery", ["discovery receipt"]),
    ("catalog-draft", "Catalog draft", ["deterministic catalog YAML", "source digest"]),
    (
        "artifact-security",
        "Artifact and security review",
        ["image policy", "SBOM", "signature", "threat review"],
    ),
    (
        "one-seat-lifecycle",
        "One-seat lifecycle",
        ["provision", "participant journey", "restart", "reclaim", "zero residue"],
    ),
    ("target-qualification", "Execution target qualification", ["cluster evidence"]),
    ("human-approval", "Human approval", ["approval history", "rollback release"]),
    ("catalog-publication", "Immutable publication", ["release receipt"]),
)


def build_catalog_intake_pipeline_view(
    draft: CatalogIntakeDraft,
    *,
    isolated_worker_available: bool = False,
) -> CatalogIntakePipelineView:
    """Return a truthful, read-only view of an intake's gated future work."""

    durable = draft.storage_scope != "process-local-draft"
    first_blockers = list(draft.blockers)
    if not durable:
        first_blockers.append("Durable intake persistence is not active.")
    if not isolated_worker_available:
        first_blockers.append("An approved isolated intake worker is not available.")

    gates = []
    for index, (gate_id, label, evidence) in enumerate(GATES):
        gates.append(
            CatalogIntakePipelineGate(
                gate_id=gate_id,
                label=label,
                status="blocked" if index == 0 else "not-run",
                required_evidence=evidence,
                blockers=first_blockers if index == 0 else ["Previous gate has not passed."],
            )
        )
    stages = [
        CatalogIntakePipelineStage(
            stage_id="submitted", label="Submitted", status="current", gate_ids=[]
        ),
        CatalogIntakePipelineStage(
            stage_id="discovered",
            label="Repository discovered",
            status="locked",
            gate_ids=["repository-discovery"],
        ),
        CatalogIntakePipelineStage(
            stage_id="draft-generated",
            label="Draft generated",
            status="locked",
            gate_ids=["catalog-draft"],
        ),
        CatalogIntakePipelineStage(
            stage_id="certified",
            label="Certified",
            status="locked",
            gate_ids=["artifact-security", "one-seat-lifecycle", "target-qualification"],
        ),
        CatalogIntakePipelineStage(
            stage_id="approved",
            label="Approved",
            status="locked",
            gate_ids=["human-approval"],
        ),
        CatalogIntakePipelineStage(
            stage_id="published",
            label="Published",
            status="locked",
            gate_ids=["catalog-publication"],
        ),
    ]
    return CatalogIntakePipelineView(
        intake_id=draft.intake_id,
        current_stage="submitted",
        durable_storage=durable,
        isolated_worker_available=isolated_worker_available,
        stages=stages,
        gates=gates,
    )
