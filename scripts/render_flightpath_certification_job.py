#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if "@sha256:" not in args.image:
        raise SystemExit("--image must be immutable and include @sha256:")
    template = Path("deploy/certification/flightpath/job-template.yaml").read_text()
    rendered = template.replace("__CERTIFICATION_RUNNER_IMAGE__", args.image)
    output = Path(args.output)
    output.write_text(rendered)
    subprocess.run(["oc", "create", "--dry-run=server", "-f", str(output)], check=True)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
