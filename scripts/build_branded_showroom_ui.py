#!/usr/bin/env python3
"""Apply the Launchpad brand to a pinned upstream Nookbag checkout.

The input directory must already be checked out at the reviewed upstream commit.
This script changes only the loading experience and copies the two approved logo
assets. Nookbag's application and configuration behavior remain upstream-owned.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


FALLBACK_START = "  <Suspense fallback={"
FALLBACK_END = "  }>\n    <ErrorBoundary"

BRANDED_FALLBACK = """  <Suspense fallback={
    <main aria-label=\"Red Hat and Intel lab loading\" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100vh', margin: 0, background: 'linear-gradient(145deg, #090d12 0%, #151515 55%, #102d3d 100%)' }}>
      <style>{`@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.72;transform:scale(.985)}}`}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: '2rem', animation: 'pulse 2s ease-in-out infinite' }}>
        <img src=\"./brand/redhat-logo.svg\" alt=\"Red Hat\" style={{ width: '118px', maxHeight: '92px' }} />
        <span aria-hidden=\"true\" style={{ color: '#b8bbbe', fontSize: '2rem', fontWeight: 300 }}>×</span>
        <img src=\"./brand/intel-logo.svg\" alt=\"Intel\" style={{ width: '190px', maxHeight: '92px' }} />
      </div>
    </main>
  }>
    <ErrorBoundary"""


def brand_checkout(checkout: Path, repository: Path) -> None:
    index = checkout / "src/index.tsx"
    source = index.read_text()
    start = source.find(FALLBACK_START)
    end = source.find(FALLBACK_END, start)
    if start < 0 or end < 0:
        raise SystemExit("Pinned Nookbag loading boundary changed; review upstream before release")
    source = source[:start] + BRANDED_FALLBACK + source[end + len(FALLBACK_END) :]
    if "Demo Platform" in source:
        raise SystemExit("Legacy Demo Platform branding remains in Nookbag entry point")
    index.write_text(source)

    brand_dir = checkout / "src/public/brand"
    brand_dir.mkdir(parents=True, exist_ok=True)
    for logo in ("redhat-logo.svg", "intel-logo.svg"):
        shutil.copyfile(repository / "content/supplemental-ui/img" / logo, brand_dir / logo)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    brand_checkout(args.checkout.resolve(), args.repository.resolve())


if __name__ == "__main__":
    main()
