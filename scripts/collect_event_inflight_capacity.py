"""Fail-closed entry point for future in-flight capacity evidence collection.

No live cluster observer is shipped yet. Supplying an output path never writes
an admission-ready file without a complete read-only adapter and persisted
reservation/seat inventory. This script deliberately does not use kubeadmin,
the current oc context, or ambient kubeconfig credentials.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.parse_args(argv)
    print(
        "Blocked: no trusted complete cluster observer and persisted seat adapter "
        "are configured; no capacity snapshot was written.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
