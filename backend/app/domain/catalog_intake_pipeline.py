from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CatalogIntakePipelineGate(BaseModel):
    gate_id: str
    label: str
    status: Literal["blocked", "not-run", "passed", "failed"]
    required_evidence: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class CatalogIntakePipelineStage(BaseModel):
    stage_id: str
    label: str
    status: Literal["current", "locked", "complete"]
    gate_ids: list[str]


class CatalogIntakePipelineActions(BaseModel):
    run_discovery: bool = False
    generate_draft: bool = False
    run_one_seat_certification: bool = False
    request_review: bool = False
    promote: bool = False


class CatalogIntakePipelineView(BaseModel):
    schema_version: Literal["launchpad.redhat.com/catalog-intake-pipeline/v1"] = (
        "launchpad.redhat.com/catalog-intake-pipeline/v1"
    )
    intake_id: str
    source_standard: Literal["quickstart-repository"] = "quickstart-repository"
    metadata_policy: Literal["discover-from-source"] = "discover-from-source"
    current_stage: Literal["submitted"] = "submitted"
    orderable: Literal[False] = False
    promotion_eligible: Literal[False] = False
    durable_storage: bool
    isolated_worker_available: bool
    stages: list[CatalogIntakePipelineStage]
    gates: list[CatalogIntakePipelineGate]
    actions: CatalogIntakePipelineActions = Field(default_factory=CatalogIntakePipelineActions)
