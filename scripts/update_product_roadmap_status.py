#!/usr/bin/env python3
"""Record one roadmap proof result and regenerate the clickable dashboard.

Example:
  python3 scripts/update_product_roadmap_status.py \
    --task LP-T008 --method tdd --stage green-local \
    --evidence evidence/runs/catalog-image-test.json

The command never grants rubric points. Rubric acceptance remains an explicit
product-owner decision in docs/product-roadmap-status.json.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "product-roadmap-status.json"
ROADMAP = ROOT / "docs" / "product-delivery-roadmap.md"
METHODS = ("tdd", "edd", "cdd", "bdd", "cbt")
STAGES = ("red", "green-local", "green-integration", "green-live")


def known_task_ids() -> set[str]:
    return set(re.findall(r"LP-T\d{3}", ROADMAP.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--method", required=True, choices=METHODS)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--note")
    args = parser.parse_args()

    if args.task not in known_task_ids():
        parser.error(f"unknown roadmap task: {args.task}")
    missing = [item for item in args.evidence if not (ROOT / item).exists()]
    if missing:
        parser.error(f"evidence does not exist: {', '.join(missing)}")

    ledger = json.loads(STATUS.read_text(encoding="utf-8"))
    task = ledger.setdefault("tasks", {}).setdefault(args.task, {})
    task["state"] = args.stage
    task.setdefault("methods", {})[args.method] = args.stage
    task["evidence"] = sorted(set(task.get("evidence", []) + args.evidence))
    if args.note is not None:
        task["note"] = args.note
    ledger["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    STATUS.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_product_roadmap_dashboard.py")],
        cwd=ROOT,
        check=True,
    )
    print(f"recorded: {args.task} {args.method.upper()} {args.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
