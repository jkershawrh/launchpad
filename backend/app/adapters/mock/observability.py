from __future__ import annotations

from typing import Any, Dict

from app.domain.models import LabSession


class MockObservabilityAdapter:
    def create_dashboard(self, session: LabSession) -> str:
        return f"https://dashboard.example.com/{session.namespace}"

    def get_metrics(self, session_id: str) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "cpu_usage_percent": 12.5,
            "memory_usage_percent": 34.0,
            "pod_count": 3,
            "request_count": 42,
        }

    def get_health(self, session_id: str) -> str:
        return "healthy"
