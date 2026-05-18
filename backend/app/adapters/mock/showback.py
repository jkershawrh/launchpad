from __future__ import annotations

import json
from typing import Any, Dict

from app.domain.models import LabSession, ShowbackRecord


class MockShowbackAdapter:
    def __init__(self) -> None:
        self._records: Dict[str, ShowbackRecord] = {}

    def create_record(self, session: LabSession) -> ShowbackRecord:
        record = ShowbackRecord(
            tenant_id=session.tenant_id,
            session_id=session.session_id,
            catalog_item_id=session.catalog_item_id,
            namespace=session.namespace,
            duration_seconds=14400,
            cpu_requested="8",
            cpu_used_estimate="3.2",
            memory_requested="16Gi",
            memory_used_estimate="6Gi",
            storage_requested="50Gi",
            storage_used_estimate="12Gi",
            gaudi_endpoint_requests=150,
            model_requests=150,
            estimated_tokens=75000,
        )
        self._records[session.session_id] = record
        return record

    def summarize(self, tenant_id: str) -> Dict[str, Any]:
        tenant_records = [r for r in self._records.values() if r.tenant_id == tenant_id]
        return {
            "tenant_id": tenant_id,
            "total_sessions": len(tenant_records),
            "total_duration_seconds": sum(r.duration_seconds for r in tenant_records),
            "total_model_requests": sum(r.model_requests for r in tenant_records),
            "total_estimated_tokens": sum(r.estimated_tokens for r in tenant_records),
        }

    def export_report(self, session_id: str, fmt: str = "json") -> str:
        record = self._records.get(session_id)
        if not record:
            return "{}"
        return record.model_dump_json(indent=2)
