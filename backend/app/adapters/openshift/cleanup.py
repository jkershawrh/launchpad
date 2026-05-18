from __future__ import annotations

import subprocess
from typing import Optional


class OpenShiftCleanupAdapter:
    def cleanup(self, namespace: Optional[str] = None) -> bool:
        if not namespace:
            return False

        try:
            result = subprocess.run(
                ["oc", "delete", "project", namespace],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False
