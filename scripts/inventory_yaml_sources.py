#!/usr/bin/env python3
"""Generate a privacy-safe inventory and consumer map for tracked YAML files.

The inventory intentionally records metadata, never YAML values. It is a
discovery artifact, not authority to delete, move, or deploy a manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT = ROOT / "evidence" / "yaml-cleanup" / "inventory-v1.json"
MARKDOWN_OUTPUT = ROOT / "docs" / "yaml-inventory-v1.md"
YAML_SUFFIXES = (".yaml", ".yml")
ENVIRONMENT_MARKERS = ("arena", "brutus", "flightpath", "oberon", "infra01")
RUNTIME_FIELDS = ("resourceVersion", "uid", "creationTimestamp", "managedFields")
GENERATED_REFERENCE_OUTPUTS = {
    "docs/yaml-inventory-v1.md",
    "evidence/yaml-cleanup/inventory-v1.json",
}


def _git(*args: str) -> str:
    return subprocess.check_output(
        ("git", *args), cwd=ROOT, text=True, stderr=subprocess.DEVNULL
    )


def tracked_files() -> list[str]:
    output = _git("ls-files", "-z")
    return sorted(
        path
        for path in output.split("\0")
        if path and (ROOT / path).is_file()
    )


def classify(path: str) -> str:
    if path.startswith("contracts/"):
        return "contract"
    if path.startswith(("evidence/", "certification/")):
        return "evidence"
    if path.startswith("fixtures/"):
        return "fixture"
    if path.startswith("catalog-onboarding/"):
        return "generated-intake"
    if path.startswith("catalog/"):
        return "catalog-source"
    if path.startswith("tenant/"):
        return "tenant-source"
    if path.startswith(".github/"):
        return "ci"
    if path.startswith("deploy/"):
        if "/templates/" in path:
            return "deployment-template"
        return "deployment-source"
    if path.startswith("demos/"):
        return "demo-source"
    if path.startswith("config/"):
        return "configuration"
    if path.startswith(("content", "site")):
        return "content-source"
    return "repository-configuration"


def area(path: str) -> str:
    parts = Path(path).parts
    if path.startswith("deploy/launchpad/overlays/") and len(parts) >= 4:
        return "/".join(parts[:4])
    if path.startswith("deploy/workloads/") and len(parts) >= 3:
        return "/".join(parts[:3])
    return parts[0]


def governance(path: str, classification: str) -> dict[str, Any]:
    """Assign role stewardship while keeping every cleanup decision fail closed."""

    if classification == "contract":
        return {
            "owner": "contract-governance-owner",
            "protection_class": "authoritative-contract",
            "proposed_disposition": "preserve-authoritative",
        }
    if classification == "evidence":
        return {
            "owner": "evidence-governance-owner",
            "protection_class": "immutable-evidence",
            "proposed_disposition": "preserve-history",
        }
    if classification in {"catalog-source", "generated-intake"}:
        return {
            "owner": "catalog-release-owner",
            "protection_class": "catalog-release-input",
            "proposed_disposition": "preserve-release-input",
        }
    if classification in {
        "deployment-source",
        "deployment-template",
        "configuration",
        "tenant-source",
    }:
        return {
            "owner": "platform-release-owner",
            "protection_class": "runtime-or-deployment-input",
            "proposed_disposition": "preserve-runtime-input",
        }
    if classification in {"fixture", "ci"}:
        return {
            "owner": "quality-engineering-owner",
            "protection_class": "test-or-delivery-input",
            "proposed_disposition": "preserve-test-or-delivery-input",
        }
    if classification == "repository-configuration":
        return {
            "owner": "repository-maintenance-owner",
            "protection_class": "repository-governance-input",
            "proposed_disposition": "preserve-repository-configuration",
        }
    if classification in {"content-source", "demo-source"}:
        return {
            "owner": "experience-content-owner",
            "protection_class": "participant-content-input",
            "proposed_disposition": "preserve-content-input",
        }
    return {
        "owner": "unassigned",
        "protection_class": "scope-unresolved",
        "proposed_disposition": "preserve-pending-owner-review",
    }


def _text_files(paths: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        candidate = ROOT / path
        try:
            if candidate.stat().st_size > 2_000_000:
                continue
            result[path] = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return result


def _consumer_map(yaml_paths: list[str], texts: dict[str, str]) -> dict[str, list[str]]:
    consumers: dict[str, list[str]] = {path: [] for path in yaml_paths}
    yaml_set = set(yaml_paths)
    yaml_reference = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z0-9_.@/-]+\.ya?ml)")
    directory_reference = re.compile(r"(?m)^\s*-\s+([A-Za-z0-9_.@/-]+)\s*$")
    for source, text in texts.items():
        source_parent = str(Path(source).parent)
        candidates = set(yaml_reference.findall(text))
        for raw in candidates:
            direct = posixpath.normpath(raw.removeprefix("./"))
            relative = posixpath.normpath(posixpath.join(source_parent, raw))
            for resolved in (direct, relative):
                if resolved in yaml_set and resolved != source:
                    consumers[resolved].append(source)
        if Path(source).name in {"kustomization.yaml", "kustomization.yml"}:
            for raw in directory_reference.findall(text):
                directory = posixpath.normpath(posixpath.join(source_parent, raw))
                for name in ("kustomization.yaml", "kustomization.yml"):
                    resolved = posixpath.join(directory, name)
                    if resolved in yaml_set and resolved != source:
                        consumers[resolved].append(source)
    for target, sources in consumers.items():
        consumers[target] = sorted(set(sources))
    return consumers


def _kinds(text: str) -> list[str]:
    return sorted(set(re.findall(r"(?m)^kind:\s*['\"]?([A-Za-z0-9.-]+)", text)))


def _risk_flags(path: str, text: str, kinds: list[str]) -> list[str]:
    flags: list[str] = []
    if "Secret" in kinds and re.search(r"(?m)^(data|stringData):\s*$", text):
        flags.append("secret-object-review-required")
    if any(re.search(rf"(?m)^\s*{re.escape(field)}:\s*", text) for field in RUNTIME_FIELDS):
        flags.append("possible-cluster-export-metadata")
    if re.search(r"(?m)^\s*status:\s*", text):
        flags.append("status-field-review-required")
    if re.search(r"(?m)^\s*image:\s*[^#\s]+:latest\s*$", text):
        flags.append("mutable-latest-image")
    marker_source = f"{path}\n{text}".lower()
    if any(marker in marker_source for marker in ENVIRONMENT_MARKERS):
        flags.append("environment-specific")
    return flags


def _dependency_flags(path: str, text: str) -> list[str]:
    """Classify explicit RHDP/RHPDS dependencies without recording their values.

    These are review signals, not permission to replace an image or source URL.
    A pinned upstream input may still be required by an active workload.
    """

    del path
    flags: list[str] = []
    if re.search(r"(?:github\.com|raw\.githubusercontent\.com)/rhpds/|/gh/rhpds/", text, re.IGNORECASE):
        flags.append("rhpds-git-dependency")
    if re.search(r"quay\.io/rhpds/", text, re.IGNORECASE):
        flags.append("rhpds-image-dependency")
    if re.search(r"quay\.io/redhat-gpte/", text, re.IGNORECASE):
        flags.append("redhat-gpte-image-dependency")
    if re.search(r"\bagnostic[vd]\b|\bagnosticd\.", text, re.IGNORECASE):
        flags.append("agnostic-automation-dependency")
    if re.search(r"\bdemo\.redhat\.com\b", text, re.IGNORECASE):
        flags.append("rhdp-service-dependency")
    return flags


def build_inventory(root: Path = ROOT) -> dict[str, Any]:
    del root  # The repository root is fixed deliberately for safe reproducibility.
    all_tracked = tracked_files()
    yaml_paths = [path for path in all_tracked if path.endswith(YAML_SUFFIXES)]
    # Generated inventory outputs enumerate YAML paths by design. Treating
    # those outputs as consumers would make every tracked YAML file appear to
    # have a repository reference after the first committed generation.
    reference_sources = [
        path for path in all_tracked if path not in GENERATED_REFERENCE_OUTPUTS
    ]
    texts = _text_files(reference_sources)
    consumers = _consumer_map(yaml_paths, texts)
    records: list[dict[str, Any]] = []
    for path in yaml_paths:
        text = texts.get(path, "")
        kinds = _kinds(text)
        classification = classify(path)
        governance_fields = governance(path, classification)
        markers = sorted(
            marker
            for marker in ENVIRONMENT_MARKERS
            if marker in f"{path}\n{text}".lower()
        )
        records.append(
            {
                "path": path,
                "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
                "classification": classification,
                "area": area(path),
                "kinds": kinds,
                "environment_markers": markers,
                "referenced_by": consumers[path],
                "reference_count": len(consumers[path]),
                "risk_flags": _risk_flags(path, text, kinds),
                "dependency_flags": _dependency_flags(path, text),
                **governance_fields,
                "deletion_eligible": False,
            }
        )
    classification_counts = Counter(record["classification"] for record in records)
    risk_counts = Counter(flag for record in records for flag in record["risk_flags"])
    dependency_counts = Counter(
        flag for record in records for flag in record["dependency_flags"]
    )
    protection_counts = Counter(record["protection_class"] for record in records)
    tracked_changes_present = bool(_git("status", "--porcelain", "--untracked-files=no").strip())
    return {
        "schema_version": 1,
        "kind": "YamlSourceInventory",
        "source_commit": _git("rev-parse", "HEAD").strip(),
        "source_state": "working-tree",
        "tracked_changes_present": tracked_changes_present,
        "safety_boundary": (
            "Discovery only. No record authorizes deletion, movement, secret rotation, "
            "deployment, GitOps sync, catalog activation, or live mutation."
        ),
        "summary": {
            "tracked_yaml_files": len(records),
            "unassigned_owners": sum(record["owner"] == "unassigned" for record in records),
            "preserved_pending_review": sum(
                record["proposed_disposition"].startswith("preserve-")
                for record in records
            ),
            "deletion_eligible": sum(record["deletion_eligible"] for record in records),
            "files_without_detected_repository_reference": sum(
                record["reference_count"] == 0 for record in records
            ),
            "classification_counts": dict(sorted(classification_counts.items())),
            "risk_flag_counts": dict(sorted(risk_counts.items())),
            "dependency_flag_counts": dict(sorted(dependency_counts.items())),
            "protection_class_counts": dict(sorted(protection_counts.items())),
        },
        "records": records,
    }


def render_markdown(inventory: dict[str, Any]) -> str:
    summary = inventory["summary"]
    classifications = "\n".join(
        f"| `{name}` | {count} |"
        for name, count in summary["classification_counts"].items()
    )
    risks = "\n".join(
        f"| `{name}` | {count} |"
        for name, count in summary["risk_flag_counts"].items()
    ) or "| None detected | 0 |"
    dependencies = "\n".join(
        f"| `{name}` | {count} |"
        for name, count in summary["dependency_flag_counts"].items()
    ) or "| None detected | 0 |"
    protections = "\n".join(
        f"| `{name}` | {count} |"
        for name, count in summary["protection_class_counts"].items()
    )
    flagged_paths = {
        flag: [record["path"] for record in inventory["records"] if flag in record["risk_flags"]]
        for flag in (
            "secret-object-review-required",
            "mutable-latest-image",
            "possible-cluster-export-metadata",
        )
    }

    def path_list(flag: str) -> str:
        paths = flagged_paths[flag]
        return "\n".join(f"- `{path}`" for path in paths) if paths else "- None detected"

    return f"""# YAML source inventory v1

This is the generated discovery companion to
[`yaml-cleanup-plan.md`](yaml-cleanup-plan.md). It records paths, hashes,
classifications, kinds, repository references, and risk categories only. It
does **not** copy YAML values or authorize any cleanup action.

## Safety boundary

{inventory['safety_boundary']}

An absent detected reference does not prove a file is unused. External GitOps,
CLI, documentation, and human consumers must be checked before disposition.

## Summary

- Tracked YAML/YML files: **{summary['tracked_yaml_files']}**
- Owner assignment still required: **{summary['unassigned_owners']}**
- Preserved pending owner review: **{summary['preserved_pending_review']}**
- Deletion eligible: **{summary['deletion_eligible']}**
- No repository reference detected: **{summary['files_without_detected_repository_reference']}**
- Base source commit: `{inventory['source_commit']}`
- Source state: **{inventory['source_state']}**; tracked changes present:
  **{str(inventory['tracked_changes_present']).lower()}**

## Classification

| Classification | Files |
|---|---:|
{classifications}

## Review flags

Flags identify required review; they are not findings by themselves. For
example, a domain contract may legitimately contain a `status` field.

| Flag | Files |
|---|---:|
{risks}

## Red Hat-hosted and RHDP dependency review

These counts identify YAML files with explicit external Git, image, or
automation references. They do not expose URL values and do not imply that a
reference should be removed. The approved RHPDS Launchpad repository and
Showroom content may remain; use the flags to prove portability and identify
hidden RHDP/AgnosticD requirements. Inspect the machine-readable records and
prove each active consumer before changing it.

| Dependency | Files |
|---|---:|
{dependencies}

## Protection classes

Every tracked YAML file remains deletion-ineligible until `YAML-SCOPE-001` is
approved and its external consumers are checked. Role ownership below routes
review; it is not named-human acceptance.

| Protection class | Files |
|---|---:|
{protections}

## Priority review queues

These paths require classification, not automatic modification. Secret objects
may be safe templates, `latest` may be replaced by an overlay digest, and a
runtime-looking field may be legitimate application data.

### Secret objects

{path_list('secret-object-review-required')}

### Mutable `latest` image references

{path_list('mutable-latest-image')}

### Possible cluster-export metadata

{path_list('possible-cluster-export-metadata')}

The complete machine-readable inventory is
[`../evidence/yaml-cleanup/inventory-v1.json`](../evidence/yaml-cleanup/inventory-v1.json).
"""


def _write_or_check(path: Path, content: str, check: bool) -> bool:
    if check:
        return path.exists() and path.read_text(encoding="utf-8") == content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _preserve_recorded_provenance(
    inventory: dict[str, Any], recorded: dict[str, Any]
) -> dict[str, Any]:
    """Keep generation provenance stable during freshness checks.

    A generated file cannot contain the hash of the commit that first contains
    that file. Freshness therefore compares repository-derived inventory data
    while retaining the commit and working-tree state recorded at generation.
    """

    for field in ("source_commit", "source_state", "tracked_changes_present"):
        if field in recorded:
            inventory[field] = recorded[field]
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated inventory is stale")
    args = parser.parse_args()
    inventory = build_inventory()
    if args.check and JSON_OUTPUT.exists():
        recorded = json.loads(JSON_OUTPUT.read_text(encoding="utf-8"))
        inventory = _preserve_recorded_provenance(inventory, recorded)
    json_content = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    markdown_content = render_markdown(inventory)
    results = {
        JSON_OUTPUT: _write_or_check(JSON_OUTPUT, json_content, args.check),
        MARKDOWN_OUTPUT: _write_or_check(MARKDOWN_OUTPUT, markdown_content, args.check),
    }
    stale = [path for path, current in results.items() if not current]
    if stale:
        for path in stale:
            print(f"stale: {path.relative_to(ROOT)}", file=sys.stderr)
        return 1
    for path in results:
        print(f"{'current' if args.check else 'generated'}: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
