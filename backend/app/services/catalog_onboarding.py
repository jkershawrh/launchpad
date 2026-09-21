from __future__ import annotations

import copy
import json
import re
from pathlib import Path, PurePath
from typing import Any

import yaml

IMMUTABLE_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
DISCOVERY_RECEIPT_VERSION = "launchpad.redhat.com/catalog-discovery-receipt/v1"
CATALOG_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IMAGE_REF = re.compile(r"image::([^\[]+)\[")
XREF = re.compile(r"xref:([^\[#]+)(?:#[^\[]+)?\[")
VALUE_PATH = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$")
RUNTIME_TEMPLATE_FIELD = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
SENSITIVE_RUNTIME_MARKERS = ("PASSWORD", "TOKEN", "SECRET", "API_KEY", "PRIVATE_KEY")
DISCOVERY_IGNORED_PARTS = {".git", ".venv", "node_modules", "build", "dist"}
CONTAINERFILE_NAMES = {"Containerfile", "Dockerfile"}
FROM_IMAGE = re.compile(r"(?im)^\s*FROM(?:\s+--platform=\S+)?\s+(\S+)")
IMMUTABLE_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
OPERATOR_KINDS = {"ClusterServiceVersion", "OperatorGroup", "Subscription"}
CLUSTER_SCOPED_KINDS = {
    "APIService",
    "ClusterRole",
    "ClusterRoleBinding",
    "ClusterResourceQuota",
    "CustomResourceDefinition",
    "MachineConfig",
    "Namespace",
    "Node",
    "OAuth",
    "PriorityClass",
    "SecurityContextConstraints",
    "StorageClass",
    "ValidatingWebhookConfiguration",
    "MutatingWebhookConfiguration",
}
QUALITY_SCHEMA_VERSION = "launchpad.redhat.com/catalog-intake-quality/v1"
ACTION_TITLE_VERBS = {
    "accelerate", "analyze", "automate", "boost", "build", "classify",
    "create", "deploy", "detect", "encrypt", "govern", "monitor",
    "optimize", "orchestrate", "route", "run", "scale", "secure",
    "serve", "stream", "transform",
}
QUALITY_TEXT_SUFFIXES = {
    ".adoc", ".cfg", ".conf", ".env", ".ini", ".java", ".js", ".json",
    ".md", ".py", ".sh", ".toml", ".ts", ".tsx", ".yaml", ".yml",
}
FRAMEWORK_SIGNALS = {
    "gradio", "langchain", "llama_index", "openai", "openvino", "optimum",
    "react", "streamlit", "torch", "transformers", "vllm",
}


def load_intake(path: Path | str) -> dict[str, Any]:
    """Load a repository-native catalog onboarding contract."""
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise TypeError(f"Catalog onboarding intake must be a YAML mapping: {path}")
    return data


def _repository_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return relative or "."


def _discover_showroom(root: Path) -> tuple[dict[str, str], list[str], list[str]]:
    candidates: list[dict[str, str]] = []
    warnings: list[str] = []
    errors: list[str] = []
    for playbook in sorted(root.rglob("*.y*ml")):
        if any(part in DISCOVERY_IGNORED_PARTS for part in playbook.parts):
            continue
        try:
            document = yaml.safe_load(playbook.read_text())
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        sources = (((document or {}).get("content") or {}).get("sources") or []) if isinstance(document, dict) else []
        for source in sources:
            if not isinstance(source, dict) or source.get("url") != ".":
                continue
            start_path = str(source.get("start_path", "."))
            component = root / start_path / "antora.yml"
            if component.is_file():
                candidates.append(
                    {
                        "playbook": _repository_path(root, playbook),
                        "start_path": start_path,
                    }
                )
    if not candidates:
        errors.append(
            "No Antora playbook with a local content source and matching antora.yml was discovered."
        )
        return {"playbook": "site.yml", "start_path": "."}, warnings, errors
    if len(candidates) > 1:
        warnings.append(
            "Multiple Antora sources were discovered; review the deterministic first selection."
        )
    return candidates[0], warnings, errors


def _discover_workload(root: Path) -> tuple[dict[str, str], list[str], list[str]]:
    candidates: list[tuple[int, str, str]] = []
    warnings: list[str] = []
    errors: list[str] = []

    for chart in sorted(root.rglob("Chart.yaml")):
        if any(part in DISCOVERY_IGNORED_PARTS for part in chart.parts):
            continue
        if (chart.parent / "values.yaml").is_file():
            candidates.append((0, _repository_path(root, chart.parent), "helm"))
    for kustomization in sorted(root.rglob("kustomization.y*ml")):
        if any(part in DISCOVERY_IGNORED_PARTS for part in kustomization.parts):
            continue
        candidates.append((1, _repository_path(root, kustomization.parent), "kustomize"))
    if not candidates:
        manifest_dirs: set[Path] = set()
        for manifest in sorted(root.rglob("*.y*ml")):
            if any(part in DISCOVERY_IGNORED_PARTS for part in manifest.parts):
                continue
            try:
                text = manifest.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            if re.search(r"(?m)^apiVersion:\s*\S+", text) and re.search(
                r"(?m)^kind:\s*\S+", text
            ):
                manifest_dirs.add(manifest.parent)
        for directory in sorted(manifest_dirs):
            candidates.append((2, _repository_path(root, directory), "manifests"))

    if not candidates:
        errors.append(
            "No deployable workload package (Helm, Kustomize, or Kubernetes manifests) was discovered."
        )
        return {"deployment_type": "manifests", "deploy_path": "."}, warnings, errors
    candidates.sort(key=lambda item: (item[0], item[1]))
    if len(candidates) > 1:
        warnings.append(
            "Multiple workload packages were discovered; review the deterministic first selection."
        )
    _, deploy_path, deployment_type = candidates[0]
    return {
        "deployment_type": deployment_type,
        "deploy_path": deploy_path,
    }, warnings, errors


def _append_unique(items: list[dict[str, Any]], item: dict[str, Any]) -> None:
    marker = json.dumps(item, sort_keys=True)
    if all(json.dumps(existing, sort_keys=True) != marker for existing in items):
        items.append(item)


def _walk_mappings(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def _resource_identity(document: dict[str, Any], path: str) -> dict[str, str]:
    metadata = document.get("metadata") or {}
    return {
        "api_version": str(document.get("apiVersion", "")),
        "kind": str(document.get("kind", "")),
        "name": str(metadata.get("name", "")),
        "path": path,
    }


def _container_inventory(
    document: dict[str, Any],
    path: str,
    inventory: dict[str, list[Any]],
) -> None:
    for mapping in _walk_mappings(document):
        for container_key in ("containers", "initContainers"):
            containers = mapping.get(container_key)
            if not isinstance(containers, list):
                continue
            for container in containers:
                if not isinstance(container, dict):
                    continue
                container_name = str(container.get("name", ""))
                image = container.get("image")
                if isinstance(image, str) and image.strip():
                    _append_unique(
                        inventory["images"],
                        {
                            "path": path,
                            "reference": image.strip(),
                            "source": "manifest",
                        },
                    )
                for port in container.get("ports") or []:
                    if not isinstance(port, dict) or "containerPort" not in port:
                        continue
                    _append_unique(
                        inventory["ports"],
                        {
                            "container": container_name,
                            "name": str(port.get("name", "")),
                            "path": path,
                            "port": port["containerPort"],
                            "protocol": str(port.get("protocol", "TCP")),
                        },
                    )
                resources = container.get("resources") or {}
                requests = resources.get("requests") or {}
                limits = resources.get("limits") or {}
                if requests or limits:
                    _append_unique(
                        inventory["resource_envelopes"],
                        {
                            "container": container_name,
                            "limits": {
                                str(key): str(value)
                                for key, value in sorted(limits.items())
                            },
                            "path": path,
                            "requests": {
                                str(key): str(value)
                                for key, value in sorted(requests.items())
                            },
                        },
                    )
                security_context = container.get("securityContext") or {}
                if security_context.get("privileged") is True:
                    _append_unique(
                        inventory["privileged_findings"],
                        {
                            "container": container_name,
                            "path": path,
                            "reason": "privileged container enabled",
                        },
                    )
                for env in container.get("env") or []:
                    if not isinstance(env, dict):
                        continue
                    env_name = str(env.get("name", ""))
                    value = env.get("value")
                    if (
                        "MODEL" in env_name.upper()
                        and isinstance(value, (str, int, float))
                        and not any(
                            marker in env_name.upper()
                            for marker in SENSITIVE_RUNTIME_MARKERS
                        )
                    ):
                        _append_unique(
                            inventory["models"],
                            {
                                "environment": env_name,
                                "path": path,
                                "value": str(value),
                            },
                        )


def _secret_reference_inventory(
    document: dict[str, Any],
    path: str,
    inventory: dict[str, list[Any]],
) -> None:
    for mapping in _walk_mappings(document):
        for source in ("secretKeyRef", "secretRef"):
            reference = mapping.get(source)
            if isinstance(reference, dict) and str(reference.get("name", "")).strip():
                _append_unique(
                    inventory["secret_references"],
                    {
                        "name": str(reference["name"]),
                        "path": path,
                        "source": source,
                    },
                )
        secret_volume = mapping.get("secret")
        if (
            isinstance(secret_volume, dict)
            and str(secret_volume.get("secretName", "")).strip()
        ):
            _append_unique(
                inventory["secret_references"],
                {
                    "name": str(secret_volume["secretName"]),
                    "path": path,
                    "source": "volumeSecret",
                },
            )


def _privilege_inventory(
    document: dict[str, Any],
    path: str,
    inventory: dict[str, list[Any]],
) -> None:
    for mapping in _walk_mappings(document):
        for field, reason in (
            ("hostNetwork", "hostNetwork enabled"),
            ("hostPID", "hostPID enabled"),
            ("hostIPC", "hostIPC enabled"),
        ):
            if mapping.get(field) is True:
                _append_unique(
                    inventory["privileged_findings"],
                    {"path": path, "reason": reason},
                )
        if isinstance(mapping.get("hostPath"), dict):
            _append_unique(
                inventory["privileged_findings"],
                {"path": path, "reason": "hostPath volume declared"},
            )


def _storage_inventory(
    document: dict[str, Any],
    path: str,
    inventory: dict[str, list[Any]],
) -> None:
    claims: list[dict[str, Any]] = []
    if document.get("kind") == "PersistentVolumeClaim":
        claims.append(document)
    for mapping in _walk_mappings(document):
        templates = mapping.get("volumeClaimTemplates")
        if isinstance(templates, list):
            claims.extend(item for item in templates if isinstance(item, dict))
    for claim in claims:
        metadata = claim.get("metadata") or {}
        spec = claim.get("spec") or {}
        requests = ((spec.get("resources") or {}).get("requests") or {})
        _append_unique(
            inventory["storage"],
            {
                "access_modes": [str(value) for value in spec.get("accessModes") or []],
                "name": str(metadata.get("name", "")),
                "path": path,
                "request": str(requests.get("storage", "")),
                "storage_class": str(spec.get("storageClassName", "")),
            },
        )


def _discover_repository_inventory(root: Path) -> dict[str, list[Any]]:
    """Return review-only facts without copying Secret payloads or granting support."""
    inventory: dict[str, list[Any]] = {
        "cluster_scoped_resources": [],
        "cleanup_candidates": [],
        "containerfiles": [],
        "images": [],
        "manifest_resources": [],
        "models": [],
        "mutable_images": [],
        "operators": [],
        "ports": [],
        "privileged_findings": [],
        "routes": [],
        "secret_manifests": [],
        "secret_references": [],
        "storage": [],
        "resource_envelopes": [],
        "unparsed_manifests": [],
    }

    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(
            part in DISCOVERY_IGNORED_PARTS for part in path.parts
        ):
            continue
        relative = _repository_path(root, path)
        if path.name in CONTAINERFILE_NAMES or path.name.startswith("Containerfile."):
            inventory["containerfiles"].append(relative)
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            for reference in FROM_IMAGE.findall(text):
                if reference.lower() == "scratch":
                    continue
                _append_unique(
                    inventory["images"],
                    {
                        "path": relative,
                        "reference": reference,
                        "source": "containerfile",
                    },
                )
            continue
        if path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if not re.search(r"(?m)^\s*apiVersion:\s*\S+", text) or not re.search(
            r"(?m)^\s*kind:\s*\S+", text
        ):
            continue
        try:
            documents = list(yaml.safe_load_all(text))
        except yaml.YAMLError:
            inventory["unparsed_manifests"].append(relative)
            continue
        for document in documents:
            if not isinstance(document, dict) or not document.get("kind"):
                continue
            identity = _resource_identity(document, relative)
            _append_unique(inventory["manifest_resources"], identity)
            _append_unique(inventory["cleanup_candidates"], identity)
            kind = identity["kind"]
            if kind in CLUSTER_SCOPED_KINDS or kind.startswith("Cluster"):
                _append_unique(inventory["cluster_scoped_resources"], identity)
            if kind in OPERATOR_KINDS:
                _append_unique(inventory["operators"], identity)
            if kind == "Secret":
                _append_unique(
                    inventory["secret_manifests"],
                    {"name": identity["name"], "path": relative},
                )
            if kind == "Route":
                _append_unique(
                    inventory["routes"],
                    {
                        "host": str((document.get("spec") or {}).get("host", "")),
                        "name": identity["name"],
                        "path": relative,
                    },
                )
            _container_inventory(document, relative, inventory)
            _secret_reference_inventory(document, relative, inventory)
            _privilege_inventory(document, relative, inventory)
            _storage_inventory(document, relative, inventory)

    for key, values in inventory.items():
        inventory[key] = sorted(
            values,
            key=lambda value: json.dumps(value, sort_keys=True),
        )
    inventory["mutable_images"] = [
        copy.deepcopy(image)
        for image in inventory["images"]
        if not IMMUTABLE_IMAGE.fullmatch(str(image["reference"]))
    ]
    return inventory


def _read_quality_text(path: Path) -> str:
    try:
        if path.stat().st_size > 1024 * 1024:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _quality_text_corpus(root: Path) -> str:
    parts: list[str] = []
    for path in sorted(root.rglob("*")):
        if (
            not path.is_file()
            or any(part in DISCOVERY_IGNORED_PARTS for part in path.parts)
            or (
                path.suffix.lower() not in QUALITY_TEXT_SUFFIXES
                and path.name != "Makefile"
            )
        ):
            continue
        text = _read_quality_text(path)
        if text:
            parts.append(text.lower())
    return "\n".join(parts)


def _quality_yaml_artifact(
    root: Path,
    relative: str,
    collection: str,
) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        return {"path": relative, "status": "missing", "entry_count": 0}
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {"path": relative, "status": "invalid", "entry_count": 0}
    if not isinstance(document, dict) or collection not in document:
        return {"path": relative, "status": "invalid", "entry_count": 0}
    entries = document[collection]
    if not isinstance(entries, list):
        return {"path": relative, "status": "invalid", "entry_count": 0}
    return {
        "path": relative,
        "status": "present-valid",
        "entry_count": len(entries),
    }


def discover_quickstart_quality(
    source: Path | str,
    *,
    inventory: dict[str, list[Any]],
) -> dict[str, Any]:
    """Return deterministic, review-only quality signals for one Quickstart."""

    root = Path(source).resolve()
    readme = _read_quality_text(root / "README.md")
    title_match = re.search(r"(?m)^#\s+(.+)$", readme)
    title = title_match.group(1).strip() if title_match else ""
    title_verb = title.split(maxsplit=1)[0].lower() if title else ""
    headings = {
        match.group(1).strip().lower()
        for match in re.finditer(r"(?m)^##\s+(.+?)\s*$", readme)
    }
    required_sections = {
        "architecture", "deploy", "overview", "references", "requirements",
        "repository structure", "table of contents", "tags",
    }
    business_terms = {
        "business", "customer", "outcome", "problem", "reduce", "save", "team",
    }

    artifacts = {
        "validation_matrix": _quality_yaml_artifact(
            root, "tests/validation_matrix.yaml", "stages"
        ),
        "claim_registry": _quality_yaml_artifact(
            root, "tests/claim_registry.yaml", "claims"
        ),
        "benchmark_rubric": _quality_yaml_artifact(
            root, "tests/benchmark_rubric.yaml", "benchmarks"
        ),
        "publication_test": {
            "path": "tests/publication/test_readme.py",
            "status": (
                "present"
                if (root / "tests/publication/test_readme.py").is_file()
                else "missing"
            ),
        },
        "makefile": {
            "path": "Makefile",
            "status": "present" if (root / "Makefile").is_file() else "missing",
        },
        "ci_workflows": {
            "path": ".github/workflows",
            "status": (
                "present"
                if any((root / ".github/workflows").glob("*.y*ml"))
                else "missing"
            ),
        },
    }

    pages = [
        path
        for path in sorted(root.rglob("*.adoc"))
        if "modules" in path.parts and "pages" in path.parts
    ]
    hands_on = [
        path
        for path in pages
        if path.stem.lower()
        not in {"index", "conclusion", "accessing-cluster", "01-accessing-cluster"}
    ]
    module_text = {path: _read_quality_text(path) for path in hands_on}
    thin_modules = [
        _repository_path(root, path)
        for path, text in module_text.items()
        if len([line for line in text.splitlines() if line.strip()]) < 50
    ]
    corpus = _quality_text_corpus(root)
    local_markers = (
        "vllm serve",
        "vllm_cpu_kvcache_space",
        "habana_visible_modules",
    )
    remote_markers = (
        "openai_api_base",
        "model_endpoint",
        "maas_api_url",
        "/v1/chat/completions",
    )
    local_inference = any(marker in corpus for marker in local_markers)
    remote_inference = any(marker in corpus for marker in remote_markers)
    if local_inference:
        inference_mode = "local-model"
    elif remote_inference:
        inference_mode = "remote-endpoint"
    else:
        inference_mode = "unknown"

    blocking_findings: list[str] = []
    if not readme:
        blocking_findings.append("README.md is missing or unreadable")
    if title_verb not in ACTION_TITLE_VERBS:
        blocking_findings.append("README title is not action oriented")
    missing_sections = sorted(required_sections - headings)
    if missing_sections:
        blocking_findings.append(
            "README is missing required sections: " + ", ".join(missing_sections)
        )
    for name in ("validation_matrix", "claim_registry", "benchmark_rubric"):
        if artifacts[name]["status"] != "present-valid":
            blocking_findings.append(
                f"{artifacts[name]['path']} is missing or invalid"
            )
    if artifacts["publication_test"]["status"] != "present":
        blocking_findings.append("tests/publication/test_readme.py is missing")
    if not hands_on:
        blocking_findings.append("No hands-on Showroom module was discovered")
    for label, pattern in (
        ("What you will learn", r"(?mi)^==\s+What you will learn\s*$"),
        ("See", r"(?mi)^==\s+See(?::|\s)"),
        ("Verify", r"(?mi)^===?\s+Verify\s*$"),
        ("Key takeaway", r"(?mi)^==\s+Key takeaway\s*$"),
    ):
        if hands_on and any(
            not re.search(pattern, text) for text in module_text.values()
        ):
            blocking_findings.append(
                f"One or more Showroom modules lack the {label} section"
            )
    if hands_on and any(
        'role="execute"' not in text for text in module_text.values()
    ):
        blocking_findings.append(
            "One or more Showroom modules lack an executable command block"
        )
    if thin_modules:
        blocking_findings.append(
            "One or more Showroom modules are below the content-depth threshold"
        )

    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "business_solution": {
            "status": "review-required",
            "readme_present": bool(readme),
            "title": title,
            "action_oriented_title": title_verb in ACTION_TITLE_VERBS,
            "required_sections_present": not missing_sections,
            "missing_sections": missing_sections,
            "business_language_present": any(
                term in readme.lower() for term in business_terms
            ),
            "human_review_required": True,
        },
        "artifacts": artifacts,
        "showroom": {
            "page_count": len(pages),
            "hands_on_module_count": len(hands_on),
            "execute_block_count": sum(
                text.count('role="execute"') for text in module_text.values()
            ),
            "see_section_count": sum(
                bool(re.search(r"(?mi)^==\s+See(?::|\s)", text))
                for text in module_text.values()
            ),
            "verification_section_count": sum(
                bool(re.search(r"(?mi)^===?\s+Verify\s*$", text))
                for text in module_text.values()
            ),
            "key_takeaway_count": sum(
                bool(re.search(r"(?mi)^==\s+Key takeaway\s*$", text))
                for text in module_text.values()
            ),
            "thin_modules": thin_modules,
        },
        "capacity_proposal": {
            "status": "review-required",
            "inference_mode": inference_mode,
            "framework_signals": sorted(
                signal for signal in FRAMEWORK_SIGNALS if signal in corpus
            ),
            "declared_models": copy.deepcopy(inventory.get("models", [])),
            "explicit_resource_envelopes": len(
                inventory.get("resource_envelopes", [])
            ),
            "measurement_required_before_placement": True,
        },
        "security_summary": {
            "status": "review-required",
            "mutable_image_count": len(inventory.get("mutable_images", [])),
            "cluster_scoped_resource_count": len(
                inventory.get("cluster_scoped_resources", [])
            ),
            "privileged_finding_count": len(
                inventory.get("privileged_findings", [])
            ),
            "secret_manifest_count": len(inventory.get("secret_manifests", [])),
            "unparsed_manifest_count": len(
                inventory.get("unparsed_manifests", [])
            ),
            "secret_values_included": False,
        },
        "portfolio_overlap": {
            "status": "not-run",
            "reason": "A pinned versioned portfolio inventory was not supplied.",
            "mutable_live_org_scan_allowed": False,
        },
        "gate": {
            "status": "blocked" if blocking_findings else "review-required",
            "blocking_findings": blocking_findings,
        },
        "authority": {
            "mode": "analysis-only",
            "may_modify_source": False,
            "may_publish_catalog": False,
            "may_provision": False,
            "may_certify": False,
        },
    }


def discover_quickstart_repo(
    source: Path | str,
    *,
    repo_url: str,
    revision: str,
    catalog_id: str,
    display_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Discover a quickstart repository and scaffold a fail-closed intake.

    Discovery identifies repository structure only. Resource sizing, participant
    tabs, model dependencies, identity wiring, and live certification remain
    explicit activation blockers and are never inferred from filenames.
    """
    root = Path(source).resolve()
    if not root.is_dir():
        raise ValueError(f"Quickstart source directory does not exist: {root}")
    if not CATALOG_ID.fullmatch(catalog_id):
        raise ValueError("catalog_id must be a DNS-safe kebab-case ID")
    if not display_name.strip():
        raise ValueError("display_name is required")
    if not repo_url.startswith("https://github.com/"):
        raise ValueError("repo_url must be an HTTPS GitHub URL")
    if not IMMUTABLE_GIT_SHA.fullmatch(revision):
        raise ValueError("revision must be an immutable 40-character Git SHA")

    showroom, showroom_warnings, showroom_errors = _discover_showroom(root)
    workload, workload_warnings, workload_errors = _discover_workload(root)
    inventory = _discover_repository_inventory(root)
    quality = discover_quickstart_quality(root, inventory=inventory)
    errors = showroom_errors + workload_errors
    warnings = showroom_warnings + workload_warnings

    blockers = [
        "Replace zero resource placeholders with measured per-seat resource measurements.",
        "Review required capabilities, models, participant tabs, routes, identity, and runtime Secret sources.",
        "Complete source, one-seat, five-seat, and twenty-five-seat certification gates before activation.",
    ]
    if warnings:
        blockers.append("Resolve every repository discovery warning before activation.")
    if errors:
        blockers.append("Resolve repository discovery failures before rendering or activation.")
    if inventory["mutable_images"]:
        blockers.append(
            "Review every mutable container image and replace it with an approved immutable digest."
        )
    if inventory["cluster_scoped_resources"]:
        blockers.append(
            "Review every cluster-scoped resource and document its isolation, ownership, and cleanup contract."
        )
    if inventory["privileged_findings"]:
        blockers.append(
            "Review privileged workload behavior and reject it unless an explicit security exception is approved."
        )
    if inventory["secret_manifests"]:
        blockers.append(
            "Replace each repository Secret manifest with an approved runtime Secret source before activation."
        )
    if inventory["unparsed_manifests"]:
        blockers.append(
            "Review every unparsed manifest; templating or invalid YAML prevents complete static discovery."
        )
    if quality["gate"]["status"] == "blocked":
        blockers.append(
            "Quickstart quality profile has unresolved required checks; review quality.gate.blocking_findings."
        )

    intake: dict[str, Any] = {
        "api_version": "launchpad.redhat.com/v1alpha1",
        "onboarding_contract": f"catalog-onboarding/{catalog_id}.yaml",
        "catalog": {
            "catalog_item_id": catalog_id,
            "display_name": display_name.strip(),
            "description": f"Repository-discovered onboarding draft for {display_name.strip()}.",
            "category": "guided_build",
            "version": "0.1.0",
            "status": "draft",
        },
        "sources": {
            "showroom": {
                "repo_url": repo_url,
                "revision": revision,
                "playbook": showroom["playbook"],
                "start_path": showroom["start_path"],
            },
            "workload": {
                "repo_url": repo_url,
                "revision": revision,
                "deploy_path": workload["deploy_path"],
            },
        },
        "runtime": {
            "deployment_type": workload["deployment_type"],
            "required_capabilities": ["openshift", "showroom"],
            "required_models": [],
            "seat_resources": {
                "cpu_millicores": 0,
                "memory_mib": 0,
                "pods": 0,
                "storage_gib": 0,
            },
            "tabs": [{"id": "terminal", "title": "Terminal"}],
            "allowed_exposure_policies": ["internal"],
        },
        "certification": {
            "stage": "repository-discovery",
            "max_workshop_seats": 1,
            "promotion_sequence": [1, 5, 25],
            "activation_blockers": blockers,
        },
        "quality": quality,
        "discovery": {
            "source": "quickstart-repository",
            "inventory": inventory,
            "warnings": warnings,
            "errors": errors,
            "provisional_fields": [
                "catalog.description",
                "runtime.required_capabilities",
                "runtime.required_models",
                "runtime.seat_resources",
                "runtime.tabs",
            ],
        },
    }
    report = {
        "schema": DISCOVERY_RECEIPT_VERSION,
        "discovery_status": "pass" if not errors else "fail",
        "catalog_item_id": catalog_id,
        "repo_url": repo_url,
        "revision": revision,
        "showroom": showroom,
        "workload": workload,
        "inventory": inventory,
        "quality": quality,
        "draft_intake": copy.deepcopy(intake),
        "warnings": warnings,
        "errors": errors,
    }
    return intake, report


def build_catalog_draft_from_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Render a non-orderable catalog draft from one discovery receipt.

    The receipt is self-contained so the same reviewed discovery result always
    produces the same catalog YAML. This boundary never promotes, activates,
    or relaxes repository-discovery blockers.
    """
    if not isinstance(receipt, dict):
        raise TypeError("catalog discovery receipt must be a mapping")
    if receipt.get("schema") != DISCOVERY_RECEIPT_VERSION:
        raise ValueError(
            f"catalog discovery receipt schema must be {DISCOVERY_RECEIPT_VERSION}"
        )
    if receipt.get("discovery_status") != "pass" or receipt.get("errors"):
        raise ValueError("catalog draft generation requires successful repository discovery")

    intake = receipt.get("draft_intake")
    if not isinstance(intake, dict):
        raise TypeError("catalog discovery receipt must contain a draft_intake mapping")
    catalog = intake.get("catalog") or {}
    runtime = intake.get("runtime") or {}
    certification = intake.get("certification") or {}
    sources = intake.get("sources") or {}

    receipt_catalog_id = str(receipt.get("catalog_item_id", ""))
    if str(catalog.get("catalog_item_id", "")) != receipt_catalog_id:
        raise ValueError("catalog identity differs from the repository discovery receipt")
    if catalog.get("status") != "draft":
        raise ValueError("repository discovery may generate only catalog status draft")
    if runtime.get("allowed_exposure_policies") != ["internal"]:
        raise ValueError("repository discovery draft requires internal-only exposure")
    if certification.get("max_workshop_seats") != 1:
        raise ValueError("repository discovery draft requires a one-seat ceiling")
    blockers = certification.get("activation_blockers")
    if not isinstance(blockers, list) or not blockers:
        raise ValueError(
            "repository discovery draft requires at least one unresolved activation blocker"
        )
    if (intake.get("discovery") or {}).get("inventory") != receipt.get("inventory"):
        raise ValueError("draft intake inventory differs from the repository discovery receipt")

    expected_repo = str(receipt.get("repo_url", ""))
    expected_revision = str(receipt.get("revision", ""))
    if not IMMUTABLE_GIT_SHA.fullmatch(expected_revision):
        raise ValueError("receipt revision must be an immutable 40-character Git SHA")
    for source_name in ("showroom", "workload"):
        source = sources.get(source_name) or {}
        if source.get("repo_url") != expected_repo:
            raise ValueError(
                f"{source_name} repository differs from the repository discovery receipt"
            )
        source_revision = str(source.get("revision", ""))
        if not IMMUTABLE_GIT_SHA.fullmatch(source_revision):
            raise ValueError(
                f"{source_name} revision must be an immutable 40-character Git SHA"
            )
        if source_revision != expected_revision:
            raise ValueError(
                f"{source_name} revision differs from the repository discovery receipt"
            )

    validation = validate_intake(intake)
    if validation["validation_status"] != "pass":
        raise ValueError("; ".join(validation["errors"]))
    return build_catalog_item(intake)


def build_catalog_item(intake: dict[str, Any]) -> dict[str, Any]:
    """Generate the fail-closed catalog record controlled by an intake contract."""
    catalog = intake["catalog"]
    sources = intake["sources"]
    showroom = sources["showroom"]
    workload = sources["workload"]
    runtime = intake["runtime"]
    certification = intake["certification"]
    resources = runtime["seat_resources"]
    transient_resources = runtime.get("transient_seat_resources", {})
    shared_resources = runtime.get("workshop_shared_resources", {})
    workload_contract = runtime.get("workload", {})
    references = intake.get("references", {})
    quality = intake.get("quality", {})
    capacity_metadata = {}
    track_metadata = {}
    certification_metadata = {}
    access_metadata = {}
    quality_metadata = {}
    if quality:
        quality_metadata["intake_quality"] = copy.deepcopy(quality)
    if certification.get("proof_contract"):
        certification_metadata["certification_proof_contract"] = certification[
            "proof_contract"
        ]
    if "production_blockers" in certification:
        certification_metadata["production_blockers"] = copy.deepcopy(
            certification["production_blockers"]
        )
    if "allowed_exposure_policies" in runtime:
        access_metadata["allowed_exposure_policies"] = copy.deepcopy(
            runtime["allowed_exposure_policies"]
        )
    if "learning_tracks" in runtime:
        tracks = copy.deepcopy(runtime.get("learning_tracks", []))
        track_metadata = {
            "single_environment": bool(runtime.get("single_environment", False)),
            "track_count": len(tracks),
            "learning_tracks": tracks,
        }
    if transient_resources:
        capacity_metadata.update({
            "seat_transient_cpu_millicores": transient_resources["cpu_millicores"],
            "seat_transient_memory_mib": transient_resources["memory_mib"],
            "seat_transient_pods": transient_resources["pods"],
        })
    if shared_resources:
        capacity_metadata.update({
            "workshop_shared_cpu_millicores": shared_resources["cpu_millicores"],
            "workshop_shared_memory_mib": shared_resources["memory_mib"],
            "workshop_shared_pods": shared_resources["pods"],
        })

    return {
        "catalog_item_id": catalog["catalog_item_id"],
        "display_name": catalog["display_name"],
        "description": catalog["description"],
        "category": catalog["category"],
        "version": catalog["version"],
        # Intake-generated entries default to non-orderable. A reviewed
        # promotion may persist an explicit active status only after its
        # activation blockers are empty.
        "status": catalog.get("status", "draft"),
        "required_capabilities": runtime["required_capabilities"],
        "default_hardware_profile": runtime.get("default_hardware_profile", "xeon-basic"),
        "default_quota_profile": runtime.get("default_quota_profile", "large"),
        "default_ttl": runtime.get("default_ttl", "4h"),
        "provisioner_refs": runtime.get("provisioner_refs", ["helm-workload", "showroom"]),
        "validation_refs": runtime.get(
            "validation_refs",
            [
                "pod-ready",
                "route-accessible",
                "inference-health",
                "agentops-journey",
            ],
        ),
        "observability_profile": runtime.get("observability_profile", "agentops-full-stack"),
        "supported_branding": catalog.get(
            "supported_branding", ["redhat-intel-default", "intel-internal"]
        ),
        "metadata": {
            "showroom": True,
            "operator_workshop": True,
            "content_only": False,
            "onboarding_managed": True,
            "onboarding_contract": intake.get(
                "onboarding_contract",
                f"catalog-onboarding/{catalog['catalog_item_id']}.yaml",
            ),
            "certification_stage": certification["stage"],
            "max_workshop_seats": certification["max_workshop_seats"],
            "promotion_sequence": certification["promotion_sequence"],
            "activation_blockers": certification["activation_blockers"],
            **certification_metadata,
            **access_metadata,
            "showroom_journey": catalog["catalog_item_id"],
            "showroom_title": catalog["display_name"],
            "namespace_slug": runtime.get("namespace_slug", catalog["catalog_item_id"]),
            "showroom_content_repo_url": showroom["repo_url"],
            "showroom_content_ref": showroom["revision"],
            "showroom_content_playbook": showroom["playbook"],
            "showroom_content_start_path": showroom["start_path"],
            "showroom_terminal_storage": bool(
                runtime.get("showroom_terminal_storage", True)
            ),
            "showroom_tabs": runtime["tabs"],
            **(
                {"workshop_cluster_ref": runtime["workshop_cluster_ref"]}
                if runtime.get("workshop_cluster_ref")
                else {}
            ),
            "required_models": runtime["required_models"],
            "inference_endpoint": runtime.get("inference_endpoint", "litellm"),
            "seat_cpu_millicores": resources["cpu_millicores"],
            "seat_memory_mib": resources["memory_mib"],
            "seat_pods": resources["pods"],
            "seat_storage_gib": resources["storage_gib"],
            **capacity_metadata,
            **track_metadata,
            "workshop_provision_concurrency": int(
                runtime.get("workshop_provision_concurrency", 5)
            ),
            "workshop_node_spread": bool(
                runtime.get("workshop_node_spread", False)
            ),
            "workshop_node_min_ready_seconds": int(
                runtime.get("workshop_node_min_ready_seconds", 900)
            ),
            "workshop_node_headroom_pods": int(
                runtime.get("workshop_node_headroom_pods", 0)
            ),
            "workshop_node_required_labels": dict(
                runtime.get("workshop_node_required_labels", {}) or {}
            ),
            "workload_repo": workload["repo_url"],
            "workload_revision": workload["revision"],
            "workload_deploy_type": runtime["deployment_type"],
            "workload_deployment_scope": runtime.get("deployment_scope", "seat"),
            "workload_deploy_path": workload["deploy_path"],
            "workload_source_kind": workload_contract.get("source_kind", "chart"),
            "workload_gitops_ready": bool(workload_contract.get("gitops_ready", False)),
            "workload_release_name": workload_contract.get(
                "release_name", catalog["catalog_item_id"]
            ),
            "workload_helm_values": workload_contract.get("helm_values", {}),
            "workload_ignore_differences": workload_contract.get(
                "ignore_differences", []
            ),
            "workload_runtime_secret_name": workload_contract.get("runtime_secret_name", ""),
            "workload_runtime_secret_sources": workload_contract.get("runtime_secret_sources", {}),
            "workload_runtime_secret_value_path": workload_contract.get(
                "runtime_secret_value_path", ""
            ),
            "workload_identity_value_path": workload_contract.get("identity_value_path", ""),
            "workload_routes": workload_contract.get("routes", {}),
            "workload_readiness": workload_contract.get("readiness", []),
            "source_content_repo": showroom["repo_url"],
            "source_content_revision": showroom["revision"],
            "source_references": references,
            **quality_metadata,
        },
    }


def _required_mapping(
    parent: dict[str, Any], key: str, errors: list[str], location: str
) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{location}.{key} must be a mapping")
        return {}
    return value


def _validate_contract(intake: dict[str, Any], errors: list[str]) -> None:
    if intake.get("api_version") != "launchpad.redhat.com/v1alpha1":
        errors.append("api_version must be launchpad.redhat.com/v1alpha1")

    catalog = _required_mapping(intake, "catalog", errors, "intake")
    sources = _required_mapping(intake, "sources", errors, "intake")
    runtime = _required_mapping(intake, "runtime", errors, "intake")
    certification = _required_mapping(intake, "certification", errors, "intake")
    showroom = _required_mapping(sources, "showroom", errors, "sources")
    workload = _required_mapping(sources, "workload", errors, "sources")

    catalog_id = str(catalog.get("catalog_item_id", ""))
    if not CATALOG_ID.fullmatch(catalog_id):
        errors.append("catalog.catalog_item_id must be a DNS-safe kebab-case ID")
    for key in ("display_name", "description", "category", "version"):
        if not str(catalog.get(key, "")).strip():
            errors.append(f"catalog.{key} is required")
    catalog_status = catalog.get("status", "draft")
    if catalog_status not in {"draft", "active"}:
        errors.append("catalog.status must be draft or active")

    for source_name, source in (("showroom", showroom), ("workload", workload)):
        if not str(source.get("repo_url", "")).startswith("https://github.com/"):
            errors.append(f"sources.{source_name}.repo_url must be an HTTPS GitHub URL")
        revision = str(source.get("revision", ""))
        if not IMMUTABLE_GIT_SHA.fullmatch(revision):
            errors.append(
                f"sources.{source_name}.revision must be an immutable 40-character Git SHA"
            )

    references = intake.get("references", {})
    if references and not isinstance(references, dict):
        errors.append("references must be a mapping")
    elif isinstance(references, dict):
        for reference_name, reference in references.items():
            if not isinstance(reference, dict):
                errors.append(f"references.{reference_name} must be a mapping")
                continue
            if not str(reference.get("repo_url", "")).startswith("https://github.com/"):
                errors.append(f"references.{reference_name}.repo_url must be an HTTPS GitHub URL")
            if not IMMUTABLE_GIT_SHA.fullmatch(str(reference.get("revision", ""))):
                errors.append(
                    f"references.{reference_name}.revision must be an immutable 40-character Git SHA"
                )

    if runtime.get("deployment_type") not in {"helm", "kustomize", "manifests"}:
        errors.append("runtime.deployment_type must be helm, kustomize, or manifests")
    if not isinstance(runtime.get("required_capabilities"), list):
        errors.append("runtime.required_capabilities must be a list")
    if not isinstance(runtime.get("required_models"), list):
        errors.append("runtime.required_models must be a list")
    learning_tracks = runtime.get("learning_tracks")
    if learning_tracks is not None:
        if not runtime.get("single_environment"):
            errors.append(
                "runtime.single_environment must be true when learning_tracks are declared"
            )
        if not isinstance(learning_tracks, list) or not learning_tracks:
            errors.append("runtime.learning_tracks must be a non-empty list")
        else:
            track_ids = []
            for index, track in enumerate(learning_tracks):
                location = f"runtime.learning_tracks[{index}]"
                if not isinstance(track, dict):
                    errors.append(f"{location} must be a mapping")
                    continue
                for key in ("id", "title", "showroom_page", "delivery_mode", "certification_status"):
                    if not str(track.get(key, "")).strip():
                        errors.append(f"{location}.{key} is required")
                track_id = str(track.get("id", ""))
                if track_id and not CATALOG_ID.fullmatch(track_id):
                    errors.append(f"{location}.id must be a DNS-safe kebab-case ID")
                track_ids.append(track_id)
            if len(track_ids) != len(set(track_ids)):
                errors.append("runtime.learning_tracks IDs must be unique")
    if runtime.get("deployment_scope", "seat") not in {"seat", "workshop"}:
        errors.append("runtime.deployment_scope must be seat or workshop")
    concurrency = runtime.get("workshop_provision_concurrency", 5)
    if not isinstance(concurrency, int) or concurrency < 1:
        errors.append("runtime.workshop_provision_concurrency must be a positive integer")
    node_spread = runtime.get("workshop_node_spread", False)
    if not isinstance(node_spread, bool):
        errors.append("runtime.workshop_node_spread must be a boolean")
    min_ready_seconds = runtime.get("workshop_node_min_ready_seconds", 900)
    if not isinstance(min_ready_seconds, int) or min_ready_seconds < 0:
        errors.append(
            "runtime.workshop_node_min_ready_seconds must be a non-negative integer"
        )
    headroom_pods = runtime.get("workshop_node_headroom_pods", 0)
    if not isinstance(headroom_pods, int) or headroom_pods < 0:
        errors.append(
            "runtime.workshop_node_headroom_pods must be a non-negative integer"
        )
    required_labels = runtime.get("workshop_node_required_labels", {})
    if not isinstance(required_labels, dict) or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, str)
        or not value.strip()
        for key, value in (
            required_labels.items() if isinstance(required_labels, dict) else []
        )
    ):
        errors.append(
            "runtime.workshop_node_required_labels must map non-empty strings"
        )
    workload_contract = runtime.get("workload", {})
    if workload_contract and not isinstance(workload_contract, dict):
        errors.append("runtime.workload must be a mapping")
    elif isinstance(workload_contract, dict):
        identity_path = str(workload_contract.get("identity_value_path", ""))
        if identity_path and not VALUE_PATH.fullmatch(identity_path):
            errors.append("runtime.workload.identity_value_path must be a dotted Helm value path")

        secret_name = str(workload_contract.get("runtime_secret_name", ""))
        secret_path = str(workload_contract.get("runtime_secret_value_path", ""))
        if bool(secret_name) != bool(secret_path):
            errors.append(
                "runtime.workload runtime Secret name and value path must be declared together"
            )
        if secret_path and not VALUE_PATH.fullmatch(secret_path):
            errors.append(
                "runtime.workload.runtime_secret_value_path must be a dotted Helm value path"
            )

        readiness = workload_contract.get("readiness", [])
        if not isinstance(readiness, list):
            errors.append("runtime.workload.readiness must be a list")
        else:
            for index, check in enumerate(readiness):
                location = f"runtime.workload.readiness[{index}]"
                if not isinstance(check, dict):
                    errors.append(f"{location} must be a mapping")
                    continue
                for key in ("group", "version", "plural", "name", "condition_type"):
                    if not str(check.get(key, "")).strip():
                        errors.append(f"{location}.{key} is required")
                expected_status = str(check.get("expected_status", "True"))
                if expected_status not in {"True", "False", "Unknown"}:
                    errors.append(f"{location}.expected_status must be True, False, or Unknown")
                timeout = check.get("timeout_seconds", 300)
                if not isinstance(timeout, int) or timeout < 0:
                    errors.append(f"{location}.timeout_seconds must be a non-negative integer")

        secret_sources = workload_contract.get("runtime_secret_sources", {})
        if secret_sources and not isinstance(secret_sources, dict):
            errors.append("runtime.workload.runtime_secret_sources must be a mapping")
        elif isinstance(secret_sources, dict):
            source_keys = {str(key) for key in secret_sources}
            for raw_key, field_contract in secret_sources.items():
                key = str(raw_key)
                if isinstance(field_contract, str):
                    if field_contract not in {
                        "maas_api_key",
                        "maas_api_url",
                        "maas_endpoint",
                        "requested_model",
                        "namespace",
                    }:
                        errors.append(
                            f"Runtime Secret field '{key}' uses unsupported source '{field_contract}'"
                        )
                    continue
                if not isinstance(field_contract, dict):
                    errors.append(f"Runtime Secret field '{key}' must be a source mapping")
                    continue
                declared = [
                    name for name in ("source", "value", "template") if name in field_contract
                ]
                if len(declared) != 1:
                    errors.append(
                        f"Runtime Secret field '{key}' must declare exactly one of source, value, or template"
                    )
                    continue
                if "value" in field_contract and any(
                    marker in key.upper() for marker in SENSITIVE_RUNTIME_MARKERS
                ):
                    errors.append(
                        f"Sensitive runtime field '{key}' cannot contain a catalog literal"
                    )
                if "source" in field_contract:
                    source = str(field_contract["source"])
                    if source not in {
                        "generated_password",
                        "maas_api_key",
                        "maas_api_url",
                        "maas_endpoint",
                        "model_endpoint",
                        "requested_model",
                        "namespace",
                    }:
                        errors.append(
                            f"Runtime Secret field '{key}' uses unsupported source '{source}'"
                        )
                    if source == "generated_password":
                        length = field_contract.get("length", 32)
                        if not isinstance(length, int) or not 24 <= length <= 128:
                            errors.append(
                                f"Generated runtime field '{key}' length must be between 24 and 128"
                            )
                    if (
                        source == "model_endpoint"
                        and not str(field_contract.get("model", "")).strip()
                    ):
                        errors.append(
                            f"Runtime Secret field '{key}' using model_endpoint must declare model"
                        )
                if "template" in field_contract:
                    template = str(field_contract["template"])
                    fields = set(RUNTIME_TEMPLATE_FIELD.findall(template))
                    if not fields or not fields.issubset(source_keys):
                        errors.append(
                            f"Runtime Secret template for '{key}' references unknown fields"
                        )
    resources = _required_mapping(runtime, "seat_resources", errors, "runtime")
    for key in ("cpu_millicores", "memory_mib", "pods", "storage_gib"):
        value = resources.get(key)
        if not isinstance(value, int) or value < 0:
            errors.append(f"runtime.seat_resources.{key} must be a non-negative integer")
    for resource_group in (
        "transient_seat_resources",
        "workshop_shared_resources",
    ):
        if resource_group not in runtime:
            continue
        group = runtime.get(resource_group)
        if not isinstance(group, dict):
            errors.append(f"runtime.{resource_group} must be a mapping")
            continue
        for key in ("cpu_millicores", "memory_mib", "pods"):
            value = group.get(key)
            if not isinstance(value, int) or value < 0:
                errors.append(
                    f"runtime.{resource_group}.{key} must be a non-negative integer"
                )

    tabs = runtime.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        errors.append("runtime.tabs must contain at least one tab")
    elif len({tab.get("id") for tab in tabs if isinstance(tab, dict)}) != len(tabs):
        errors.append("runtime.tabs IDs must be unique")

    blockers = certification.get("activation_blockers")
    if not isinstance(blockers, list):
        errors.append("certification.activation_blockers must be a list")
    elif catalog_status == "active" and blockers:
        errors.append("catalog.status active requires zero activation blockers")
    production_blockers = certification.get("production_blockers")
    if production_blockers is not None and not isinstance(production_blockers, list):
        errors.append("certification.production_blockers must be a list")
    allowed_exposure_policies = runtime.get("allowed_exposure_policies")
    if allowed_exposure_policies is not None and (
        not isinstance(allowed_exposure_policies, list)
        or not allowed_exposure_policies
        or any(
            value not in {"internal", "public_code"}
            for value in allowed_exposure_policies
        )
    ):
        errors.append(
            "runtime.allowed_exposure_policies must contain internal or public_code"
        )
    proof_contract = certification.get("proof_contract")
    if proof_contract is not None and (
        not isinstance(proof_contract, str)
        or not proof_contract.startswith("certification/catalog/")
        or not proof_contract.endswith(".yaml")
        or ".." in PurePath(proof_contract).parts
    ):
        errors.append(
            "certification.proof_contract must be a repository certification/catalog YAML path"
        )
    sequence = certification.get("promotion_sequence")
    if not isinstance(sequence, list) or not sequence or sequence[0] != 1:
        errors.append("certification.promotion_sequence must begin with one seat")


def _resolve_image(content_root: Path, page: Path, reference: str) -> bool:
    if reference.startswith(("http://", "https://", "data:")) or "{" in reference:
        return True
    candidates = [
        page.parent / reference,
        content_root / "modules/ROOT/images" / reference,
        content_root / "modules/ROOT/assets/images" / reference,
    ]
    return any(candidate.is_file() for candidate in candidates)


def _validate_showroom(
    source: Path, showroom: dict[str, Any], errors: list[str], warnings: list[str]
) -> None:
    errors_before_structure = len(errors)
    playbook_path = source / str(showroom.get("playbook", ""))
    content_root = source / str(showroom.get("start_path", ""))
    component_path = content_root / "antora.yml"
    nav_path = content_root / "modules/ROOT/nav.adoc"
    pages_dir = content_root / "modules/ROOT/pages"

    for label, path in (
        ("Showroom playbook", playbook_path),
        ("Antora component", component_path),
        ("Antora navigation", nav_path),
        ("Antora index", pages_dir / "index.adoc"),
    ):
        if not path.is_file():
            errors.append(f"{label} is missing: {path.relative_to(source)}")
    if len(errors) > errors_before_structure:
        return

    playbook = yaml.safe_load(playbook_path.read_text())
    sources = ((playbook or {}).get("content") or {}).get("sources") or []
    if not any(
        isinstance(entry, dict)
        and entry.get("url") == "."
        and entry.get("start_path") == showroom.get("start_path")
        for entry in sources
    ):
        errors.append("Showroom playbook does not select the declared local start_path")

    ui_bundle = (((playbook or {}).get("ui") or {}).get("bundle") or {}).get("url")
    if isinstance(ui_bundle, str) and "/latest/" in ui_bundle:
        warnings.append(
            "Showroom UI bundle uses a mutable latest URL; pin a release before activation"
        )

    pages = sorted(pages_dir.glob("*.adoc"))
    if not pages:
        errors.append("Showroom has no AsciiDoc pages")
        return

    nav = nav_path.read_text()
    for target in XREF.findall(nav):
        if not (pages_dir / target).is_file():
            errors.append(f"Showroom navigation references missing page: {target}")

    for page in pages:
        for image_ref in IMAGE_REF.findall(page.read_text()):
            image_ref = image_ref.strip()
            if not _resolve_image(content_root, page, image_ref):
                errors.append(f"Showroom page {page.name} references missing image: {image_ref}")

    if not (source / "ui-config.yml").is_file():
        warnings.append(
            "Source Showroom has no ui-config.yml; Launchpad must generate all runtime tabs"
        )


def _validate_workload(
    source: Path,
    workload: dict[str, Any],
    deployment_type: str,
    errors: list[str],
) -> None:
    deploy_path = source / str(workload.get("deploy_path", ""))
    if not deploy_path.is_dir():
        errors.append(f"Workload deploy path is missing: {deploy_path.relative_to(source)}")
        return
    required = {
        "helm": ("Chart.yaml", "values.yaml"),
        "kustomize": ("kustomization.yaml",),
        "manifests": (),
    }[deployment_type]
    for name in required:
        if not (deploy_path / name).is_file():
            errors.append(f"Workload {deployment_type} package is missing {name}")
    if deployment_type == "manifests" and not list(deploy_path.glob("*.y*ml")):
        errors.append("Workload manifest package contains no YAML files")


def validate_intake(
    intake: dict[str, Any],
    *,
    showroom_dir: Path | str | None = None,
    workload_dir: Path | str | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an intake and, when supplied, its checked-out source trees."""
    intake = copy.deepcopy(intake)
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, str] = {}
    _validate_contract(intake, errors)
    checks["intake_contract"] = "pass" if not errors else "fail"

    if showroom_dir is not None and (intake.get("sources") or {}).get("showroom"):
        before = len(errors)
        _validate_showroom(Path(showroom_dir), intake["sources"]["showroom"], errors, warnings)
        checks["showroom_structure"] = "pass" if len(errors) == before else "fail"
    else:
        checks["showroom_structure"] = "not-run" if showroom_dir is None else "fail"

    if (
        workload_dir is not None
        and (intake.get("sources") or {}).get("workload")
        and (intake.get("runtime") or {}).get("deployment_type")
    ):
        before = len(errors)
        _validate_workload(
            Path(workload_dir),
            intake["sources"]["workload"],
            intake["runtime"]["deployment_type"],
            errors,
        )
        checks["workload_structure"] = "pass" if len(errors) == before else "fail"
    else:
        checks["workload_structure"] = "not-run" if workload_dir is None else "fail"

    if catalog is not None:
        if catalog == build_catalog_item(intake):
            checks["catalog_drift"] = "pass"
        else:
            checks["catalog_drift"] = "fail"
            errors.append("Generated catalog item differs from the committed catalog item")
    else:
        checks["catalog_drift"] = "not-run" if catalog is None else "fail"

    blockers = (intake.get("certification") or {}).get("activation_blockers") or []
    return {
        "catalog_item_id": (intake.get("catalog") or {}).get("catalog_item_id"),
        "validation_status": "pass" if not errors else "fail",
        "activation_status": "blocked" if blockers or errors else "eligible",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "activation_blockers": blockers,
        "source_revisions": {
            name: source.get("revision")
            for name, source in (intake.get("sources") or {}).items()
            if isinstance(source, dict)
        },
    }
