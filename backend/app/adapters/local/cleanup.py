from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional


class LocalCleanupAdapter:
    def cleanup(self, compose_file: Optional[str] = None) -> bool:
        if not compose_file:
            compose_file = str(
                Path(__file__).resolve().parents[4] / "demos" / "podman-compose.yaml"
            )

        if not Path(compose_file).exists():
            return False

        result = subprocess.run(
            [sys.executable, "-m", "podman_compose", "-f", compose_file, "down"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path(compose_file).parent),
        )

        return result.returncode == 0
