from __future__ import annotations

import copy
import re
from pathlib import Path, PurePath
from typing import Any

import yaml

IMMUTABLE_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
CATALOG_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IMAGE_REF = re.compile(r"image::([^\[]+)\[")
XREF = re.compile(r"xref:([^\[#]+)(?:#[^\[]+)?\[")
VALUE_PATH = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$")
RUNTIME_TEMPLATE_FIELD = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
SENSITIVE_RUNTIME_MARKERS = ("PASSWORD", "TOKEN", "SECRET", "API_KEY", "PRIVATE_KEY")
DISCOVERY_IGNORED_PARTS = {".git", ".venv", "node_modules", "build", "dist"}


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
        "discovery": {
            "source": "quickstart-repository",
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
        "discovery_status": "pass" if not errors else "fail",
        "catalog_item_id": catalog_id,
        "repo_url": repo_url,
        "revision": revision,
        "showroom": showroom,
        "workload": workload,
        "warnings": warnings,
        "errors": errors,
    }
    return intake, report


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
    capacity_metadata = {}
    track_metadata = {}
    certification_metadata = {}
    access_metadata = {}
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
