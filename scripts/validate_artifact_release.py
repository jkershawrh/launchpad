#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.catalog_supply_chain import evaluate_artifact_release_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a source-to-image artifact release evidence receipt."
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "config/artifact-registry-policy.yaml",
    )
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate_artifact_release_evidence(args.policy, args.receipt)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if report["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
