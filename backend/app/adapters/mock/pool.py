from __future__ import annotations

from typing import Any, Dict


class MockPoolAdapter:
    def __init__(self) -> None:
        self._reservations: Dict[str, Dict[str, Any]] = {}

    def check_capacity(self, hardware_profile: str, quota_profile: str) -> bool:
        return True

    def reserve(self, session_id: str, hardware_profile: str, quota_profile: str) -> Dict[str, Any]:
        reservation = {
            "session_id": session_id,
            "hardware_profile": hardware_profile,
            "quota_profile": quota_profile,
            "status": "reserved",
        }
        self._reservations[session_id] = reservation
        return reservation

    def release(self, session_id: str) -> bool:
        if session_id in self._reservations:
            del self._reservations[session_id]
            return True
        return False

    def report_allocation(self) -> Dict[str, Any]:
        return {
            "total_reservations": len(self._reservations),
            "reservations": list(self._reservations.values()),
        }


class MockFullPoolAdapter:
    def check_capacity(self, hardware_profile: str, quota_profile: str) -> bool:
        return False

    def reserve(self, session_id: str, hardware_profile: str, quota_profile: str) -> Dict[str, Any]:
        raise RuntimeError("No capacity available")

    def release(self, session_id: str) -> bool:
        return False

    def report_allocation(self) -> Dict[str, Any]:
        return {"total_reservations": 0, "reservations": []}
