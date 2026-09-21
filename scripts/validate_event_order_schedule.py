#!/usr/bin/env python3
"""Validate a proposed event ordering schedule without lifecycle mutations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.events import EventManifest
from app.services.event_order_schedule import (
    EventOrderSchedule,
    evaluate_event_order_schedule,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate manifest-bound serial workshop order windows."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = yaml.safe_load(args.manifest.read_text())
    if isinstance(source, dict) and "spec" in source:
        source = source["spec"]
    manifest = EventManifest.model_validate(source)
    schedule = EventOrderSchedule.model_validate(yaml.safe_load(args.schedule.read_text()))
    decision = evaluate_event_order_schedule(manifest, schedule)
    rendered = json.dumps(decision.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if decision.eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
