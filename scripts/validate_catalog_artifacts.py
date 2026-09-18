#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.catalog_supply_chain import build_supply_chain_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed on mutable or execution-cluster-local catalog artifacts."
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "config/catalog-artifact-policy.yaml",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_supply_chain_report(args.policy, ROOT)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if report["status"] == "GREEN-local" else 1


if __name__ == "__main__":
    raise SystemExit(main())
