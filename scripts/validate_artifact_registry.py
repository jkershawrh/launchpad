#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.catalog_supply_chain import build_registry_policy_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the fail-closed authoritative artifact-registry contract."
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "config/artifact-registry-policy.yaml",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-release-ready",
        action="store_true",
        help="also fail until every integration/live registry gate is proven",
    )
    args = parser.parse_args()

    report = build_registry_policy_report(args.policy)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")

    if report["contract_status"] != "GREEN-local":
        return 1
    if args.require_release_ready and not report["release_eligible"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
