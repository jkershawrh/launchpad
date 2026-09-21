"""Explicit local invocation; no scheduler, deployment, or cluster mutation."""

import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.event_model_health_collector import (
    ModelHealthCollector,
    load_model_probe_targets,
    write_model_health_snapshot,
)


def main() -> int:
    source = os.environ.get("EVENT_MODEL_HEALTH_PROBE_CONFIG_FILE")
    destination = os.environ.get("EVENT_MODEL_HEALTH_SNAPSHOT_FILE")
    if not source or not destination:
        print("Model probe configuration and snapshot destination are required", file=sys.stderr)
        return 2
    try:
        targets = load_model_probe_targets(source)
        with httpx.Client(timeout=10.0, verify=True, follow_redirects=False) as client:
            document = ModelHealthCollector(client=client).collect(targets)
        write_model_health_snapshot(destination, document)
    except (OSError, ValueError, TypeError, KeyError, httpx.HTTPError):
        # Do not expose endpoint, token, or response details in logs.
        print("Model-health collection failed; prior evidence was not refreshed", file=sys.stderr)
        return 1
    print(f"Model-health snapshot refreshed for {len(targets)} configured model(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
