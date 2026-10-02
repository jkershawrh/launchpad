#!/usr/bin/env python3
"""Render the pinned Triforce 201 manifests with Launchpad-safe Route names.

Only Route ``metadata.name`` may change. Deployments, Services, selectors,
ports, target Services, images, probes, and environment remain the exact
objects published by the pinned Triforce revision.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import yaml


WORKLOAD_REVISION = "095132b68bec5696e384fa1304702fa3c460cccb"
RAW_PREFIX = (
    "https://raw.githubusercontent.com/rhpds/triforce/"
    f"{WORKLOAD_REVISION}/infrastructure/manifests-201/"
)
ROUTE_ALIASES = {
    "solution-tools": "tools",
    "solution-agent": "agent",
    "solution-ui": "app",
}


def _read_source(source: str) -> str:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        if not source.startswith(RAW_PREFIX):
            raise ValueError("source must use the exact pinned Triforce 201 revision")
        with urlopen(source, timeout=30) as response:  # noqa: S310 - pinned allowlist
            return response.read().decode("utf-8")
    return Path(source).read_text(encoding="utf-8")


def adapt_manifest(source_text: str, expected_alias: str | None = None) -> str:
    documents = [document for document in yaml.safe_load_all(source_text) if document]
    route_count = 0
    for document in documents:
        if document.get("kind") != "Route":
            continue
        route_count += 1
        original_name = document.get("metadata", {}).get("name")
        alias = ROUTE_ALIASES.get(original_name)
        if not alias:
            raise ValueError(f"unsupported Triforce Route name: {original_name!r}")
        if expected_alias and alias != expected_alias:
            raise ValueError(
                f"Route {original_name!r} maps to {alias!r}, not {expected_alias!r}"
            )
        document["metadata"]["name"] = alias
    if expected_alias and route_count != 1:
        raise ValueError("an aliased workload manifest must contain exactly one Route")
    return "\n---\n".join(
        yaml.safe_dump(document, sort_keys=False).rstrip() for document in documents
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--route-alias", choices=sorted(ROUTE_ALIASES.values()))
    args = parser.parse_args()
    try:
        sys.stdout.write(adapt_manifest(_read_source(args.source), args.route_alias))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"agent-201 manifest adapter: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
