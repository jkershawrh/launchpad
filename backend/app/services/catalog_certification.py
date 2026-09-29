"""Reusable contracts and evidence helpers for catalog workshop certification."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

API_VERSION = "launchpad.redhat.com/v1alpha1"
CATALOG_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
JSON_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
GATE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
ALLOWED_PLACEHOLDERS = {"namespace", "cluster_ref", "seat_number"}
ALLOWED_EXPOSURE_POLICIES = {"internal", "public_code"}
ALLOWED_CLEANUP_RESOURCES = {
    "namespaces",
    "applications.argoproj.io",
    "rolebindings.rbac.authorization.k8s.io",
    "persistentvolumeclaims",
    "persistentvolumes",
    "routes.route.openshift.io",
    "secrets",
}
SENSITIVE_KEYS = {
    "access_code",
    "api_key",
    "authorization",
    "client_secret",
    "credentials",
    "instructor_code",
    "maas_api_key",
    "one_time_access_code",
    "password",
    "public_code",
    "secret_value",
    "token",
}
SENSITIVE_SUFFIXES = (
    "_access_code",
    "_api_key",
    "_client_secret",
    "_password",
    "_token",
)


def load_certification_contract(path: Path | str) -> dict[str, Any]:
    """Load a repository-native catalog certification contract."""
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise TypeError(f"Catalog certification contract must be a YAML mapping: {path}")
    return data


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _scale_profiles(contract: dict[str, Any]) -> list[dict[str, Any]]:
    spec = contract.get("spec")
    if not isinstance(spec, dict):
        return []
    profiles = spec.get("scale_profiles")
    return profiles if isinstance(profiles, list) else []


def _profile_for_seats(contract: dict[str, Any], seats: int) -> dict[str, Any]:
    for profile in _scale_profiles(contract):
        if isinstance(profile, dict) and profile.get("seats") == seats:
            return profile
    raise ValueError(f"Certification contract does not declare a {seats}-seat profile")


def validate_certification_contract(
    contract: dict[str, Any],
    *,
    intake: dict[str, Any] | None = None,
    repo_root: Path | str | None = None,
    contract_path: Path | str | None = None,
) -> list[str]:
    """Return every contract error so onboarding fails closed in one pass."""
    errors: list[str] = []
    if contract.get("api_version") != API_VERSION:
        errors.append(f"api_version must be {API_VERSION}")
    if contract.get("kind") != "CatalogCertification":
        errors.append("kind must be CatalogCertification")

    metadata = contract.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be a mapping")
        metadata = {}
    catalog_id = str(metadata.get("catalog_item_id", ""))
    if not CATALOG_ID.fullmatch(catalog_id):
        errors.append("metadata.catalog_item_id must be a DNS-safe kebab-case ID")

    spec = contract.get("spec")
    if not isinstance(spec, dict):
        errors.append("spec must be a mapping")
        spec = {}
    if not str(spec.get("target_cluster", "")).strip():
        errors.append("spec.target_cluster is required")
    if not str(spec.get("kubeconfig_server", "")).startswith("https://"):
        errors.append("spec.kubeconfig_server must be an HTTPS API URL")

    exposure_policies = spec.get("allowed_exposure_policies")
    if (
        not isinstance(exposure_policies, list)
        or not exposure_policies
        or any(value not in ALLOWED_EXPOSURE_POLICIES for value in exposure_policies)
    ):
        errors.append(
            "spec.allowed_exposure_policies must contain only internal or public_code"
        )

    profiles = _scale_profiles(contract)
    profile_seats = [
        profile.get("seats") if isinstance(profile, dict) else None
        for profile in profiles
    ]
    if (
        not profiles
        or any(not isinstance(value, int) or value < 1 for value in profile_seats)
        or profile_seats != sorted(set(profile_seats))
        or profile_seats[0] != 1
    ):
        errors.append(
            "spec.scale_profiles must be unique, ascending positive seat counts beginning at 1"
        )
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            continue
        location = f"spec.scale_profiles[{index}]"
        seats = profile.get("seats")
        for key in (
            "required_consecutive_runs",
            "probe_concurrency",
            "maximum_ready_seconds",
            "maximum_cleanup_seconds",
        ):
            value = profile.get(key)
            if not isinstance(value, int) or value < 1:
                errors.append(f"{location}.{key} must be a positive integer")
        concurrency = profile.get("probe_concurrency")
        if isinstance(seats, int) and isinstance(concurrency, int) and concurrency > seats:
            errors.append(f"{location}.probe_concurrency cannot exceed seats")

    showroom = spec.get("showroom")
    if not isinstance(showroom, dict):
        errors.append("spec.showroom must be a mapping")
        showroom = {}
    pages = showroom.get("pages")
    seat_probe_only = showroom.get("seat_probe_only") is True
    if not isinstance(pages, list) or (not pages and not seat_probe_only):
        errors.append(
            "spec.showroom.pages must be non-empty unless seat_probe_only is true"
        )
        pages = []
    page_ids: list[str] = []
    track_ids: list[str] = []
    for index, page in enumerate(pages):
        location = f"spec.showroom.pages[{index}]"
        if not isinstance(page, dict):
            errors.append(f"{location} must be a mapping")
            continue
        page_id = str(page.get("id", ""))
        if not CATALOG_ID.fullmatch(page_id):
            errors.append(f"{location}.id must be a DNS-safe kebab-case ID")
        page_ids.append(page_id)
        if not str(page.get("path", "")).startswith("/"):
            errors.append(f"{location}.path must be an absolute URL path")
        if not str(page.get("marker", "")).strip():
            errors.append(f"{location}.marker is required")
        track_id = page.get("track_id")
        if track_id is not None:
            track_ids.append(str(track_id))
    if len(page_ids) != len(set(page_ids)):
        errors.append("spec.showroom.pages IDs must be unique")

    seat_probe = spec.get("seat_probe")
    if not isinstance(seat_probe, dict):
        errors.append("spec.seat_probe must be a mapping")
        seat_probe = {}
    argv = seat_probe.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv):
        errors.append("spec.seat_probe.argv must be a non-empty string list")
        argv = []
    if "-c" in argv or any(";" in arg or "&&" in arg or "|" in arg for arg in argv):
        errors.append("spec.seat_probe.argv shell execution is not allowed")
    placeholders = {name for arg in argv for name in PLACEHOLDER.findall(arg)}
    unknown_placeholders = placeholders - ALLOWED_PLACEHOLDERS
    if unknown_placeholders:
        errors.append(
            "spec.seat_probe.argv uses unsupported placeholders: "
            + ", ".join(sorted(unknown_placeholders))
        )
    if "namespace" not in placeholders:
        errors.append("spec.seat_probe.argv must pass the namespace placeholder")
    timeout = seat_probe.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout < 1:
        errors.append("spec.seat_probe.timeout_seconds must be a positive integer")
    if seat_probe.get("result_format") != "json":
        errors.append("spec.seat_probe.result_format must be json")
    assertions = seat_probe.get("json_assertions")
    if not isinstance(assertions, list) or not assertions:
        errors.append("spec.seat_probe.json_assertions must be a non-empty list")
        assertions = []
    for index, assertion in enumerate(assertions):
        location = f"spec.seat_probe.json_assertions[{index}]"
        if not isinstance(assertion, dict):
            errors.append(f"{location} must be a mapping")
            continue
        if not JSON_PATH.fullmatch(str(assertion.get("path", ""))):
            errors.append(f"{location}.path must be a dotted JSON path")
        operators = [
            operator
            for operator in ("equals", "length_equals", "contains")
            if operator in assertion
        ]
        if len(operators) != 1:
            errors.append(
                f"{location} must declare exactly one of equals, length_equals, or contains"
            )

    cleanup = spec.get("cleanup")
    if not isinstance(cleanup, dict):
        errors.append("spec.cleanup must be a mapping")
        cleanup = {}
    resources = cleanup.get("resources")
    if (
        not isinstance(resources, list)
        or not resources
        or any(resource not in ALLOWED_CLEANUP_RESOURCES for resource in resources)
    ):
        errors.append("spec.cleanup.resources contains an unsupported resource")

    rubric = spec.get("rubric")
    if not isinstance(rubric, dict):
        errors.append("spec.rubric must be a mapping")
        rubric = {}
    if rubric.get("required_score") != 100:
        errors.append("spec.rubric.required_score must be 100")
    categories = rubric.get("categories")
    if not isinstance(categories, list) or not categories:
        errors.append("spec.rubric.categories must be a non-empty list")
        categories = []
    total_weight = 0
    category_ids: list[str] = []
    for index, category in enumerate(categories):
        location = f"spec.rubric.categories[{index}]"
        if not isinstance(category, dict):
            errors.append(f"{location} must be a mapping")
            continue
        category_id = str(category.get("id", ""))
        if not GATE_ID.fullmatch(category_id):
            errors.append(f"{location}.id must be snake_case")
        category_ids.append(category_id)
        weight = category.get("weight")
        if not isinstance(weight, int) or weight < 1:
            errors.append(f"{location}.weight must be a positive integer")
        else:
            total_weight += weight
        requires = category.get("requires")
        if (
            not isinstance(requires, list)
            or not requires
            or any(not GATE_ID.fullmatch(str(gate)) for gate in requires)
        ):
            errors.append(f"{location}.requires must contain snake_case gate IDs")
    if len(category_ids) != len(set(category_ids)):
        errors.append("spec.rubric.categories IDs must be unique")
    if categories and total_weight != 100:
        errors.append("spec.rubric category weights must total 100")

    if intake is not None:
        intake_catalog_id = str((intake.get("catalog") or {}).get("catalog_item_id", ""))
        if catalog_id != intake_catalog_id:
            errors.append("Certification and onboarding catalog IDs must match")
        certification = intake.get("certification") or {}
        sequence = certification.get("promotion_sequence")
        if isinstance(sequence, list) and profile_seats != sequence:
            errors.append(
                "Certification scale profiles must match onboarding promotion_sequence"
            )
        if certification.get("max_workshop_seats") not in profile_seats:
            errors.append(
                "Onboarding max_workshop_seats must be a declared certification profile"
            )
        intake_track_ids = [
            str(track.get("id"))
            for track in (intake.get("runtime") or {}).get("learning_tracks", [])
            if isinstance(track, dict)
        ]
        if intake_track_ids and track_ids != intake_track_ids:
            errors.append(
                "Showroom track page IDs must match onboarding learning_tracks in order"
            )

    root = Path(repo_root).resolve() if repo_root is not None else None
    if root is not None:
        for arg in argv:
            if "{" in arg or not arg.endswith((".sh", ".py")):
                continue
            if not _safe_relative_path(arg):
                errors.append("spec.seat_probe.argv script path must stay inside the repository")
                continue
            script = (root / arg).resolve()
            if root not in script.parents or not script.is_file():
                errors.append(f"Seat probe script does not exist: {arg}")
        if contract_path is not None and intake is not None:
            proof_path = str((intake.get("certification") or {}).get("proof_contract", ""))
            try:
                relative_contract = str(Path(contract_path).resolve().relative_to(root))
            except ValueError:
                relative_contract = ""
            if proof_path != relative_contract:
                errors.append(
                    "Onboarding certification.proof_contract must reference this contract"
                )

    return errors


def build_certification_plan(
    contract: dict[str, Any],
    *,
    intake: dict[str, Any],
    seats: int,
    exposure_policy: str,
) -> dict[str, Any]:
    """Build the immutable execution plan without contacting an API or cluster."""
    errors = validate_certification_contract(contract, intake=intake)
    if errors:
        raise ValueError("Invalid certification contract: " + "; ".join(errors))
    spec = contract["spec"]
    if exposure_policy not in spec["allowed_exposure_policies"]:
        raise ValueError(
            f"Exposure policy {exposure_policy} is not certified for this catalog item"
        )
    profile = _profile_for_seats(contract, seats)
    # ``max_workshop_seats`` is the ceiling this contract is allowed to prove,
    # not evidence that the target cluster has already passed that profile.
    # Migration candidates must be able to declare a 5-seat run while starting
    # from zero Flightpath-certified seats.
    current_certified_seats = int(
        intake["certification"].get(
            "certified_seats", intake["certification"]["max_workshop_seats"]
        )
    )
    promotion_sequence = list(intake["certification"]["promotion_sequence"])
    next_targets = [value for value in promotion_sequence if value > current_certified_seats]
    next_promotion_target = next_targets[0] if next_targets else None
    certification_override = seats > current_certified_seats
    execution_eligible = not certification_override or seats == next_promotion_target
    return {
        "catalog_item_id": contract["metadata"]["catalog_item_id"],
        "cluster_ref": spec["target_cluster"],
        "kubeconfig_server": spec["kubeconfig_server"],
        "exposure_policy": exposure_policy,
        "workshop_orders": 1,
        "seats": seats,
        "seat_probe_count": seats,
        "all_seats_same_cluster": True,
        "provision_concurrency": int(
            (intake.get("runtime") or {}).get("workshop_provision_concurrency", 1)
        ),
        "probe_concurrency": profile["probe_concurrency"],
        "required_consecutive_runs": profile["required_consecutive_runs"],
        "current_certified_seats": current_certified_seats,
        "next_promotion_target": next_promotion_target,
        "certification_override": certification_override,
        "execution_eligible": execution_eligible,
        "maximum_ready_seconds": profile["maximum_ready_seconds"],
        "maximum_cleanup_seconds": profile["maximum_cleanup_seconds"],
        "showroom_pages_per_seat": len(spec["showroom"]["pages"]),
        "mutates_cluster": False,
    }


def _json_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise KeyError(path)
        value = value[key]
    return value


def evaluate_json_assertions(
    payload: dict[str, Any], assertions: list[dict[str, Any]]
) -> list[str]:
    """Check stable response structure while intentionally ignoring model prose."""
    failures: list[str] = []
    for assertion in assertions:
        path = str(assertion["path"])
        try:
            actual = _json_path(payload, path)
        except KeyError:
            failures.append(f"{path}: missing")
            continue
        if "equals" in assertion and actual != assertion["equals"]:
            failures.append(f"{path}: expected {assertion['equals']!r}, got {actual!r}")
        elif "length_equals" in assertion:
            try:
                length = len(actual)
            except TypeError:
                failures.append(f"{path}: value has no length")
            else:
                if length != assertion["length_equals"]:
                    failures.append(
                        f"{path}: expected length {assertion['length_equals']}, got {length}"
                    )
        elif "contains" in assertion:
            try:
                contains = assertion["contains"] in actual
            except TypeError:
                contains = False
            if not contains:
                failures.append(f"{path}: missing expected member {assertion['contains']!r}")
    return failures


def score_rubric(
    contract: dict[str, Any], gates: dict[str, bool]
) -> dict[str, Any]:
    """Award a category only when every gate it requires is green."""
    rubric = contract["spec"]["rubric"]
    categories: dict[str, dict[str, Any]] = {}
    score = 0
    for category in rubric["categories"]:
        passed = all(gates.get(gate, False) for gate in category["requires"])
        awarded = category["weight"] if passed else 0
        score += awarded
        categories[category["id"]] = {
            "weight": category["weight"],
            "awarded": awarded,
            "passed": passed,
            "requires": list(category["requires"]),
        }
    required = rubric["required_score"]
    return {
        "score": score,
        "required": required,
        "passed": score == required,
        "categories": categories,
    }


def evaluate_promotion(
    contract: dict[str, Any], *, seats: int, recent_results: list[bool]
) -> dict[str, Any]:
    """Require the profile's trailing consecutive successes before promotion."""
    required = _profile_for_seats(contract, seats)["required_consecutive_runs"]
    consecutive = 0
    for result in reversed(recent_results):
        if not result:
            break
        consecutive += 1
    return {
        "required_consecutive_runs": required,
        "consecutive_passing_runs": consecutive,
        "eligible": consecutive >= required,
    }


def sanitize_evidence(value: Any) -> Any:
    """Remove credential-bearing values before evidence reaches disk or stdout."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized == "authorization" and isinstance(child, dict):
                sanitized[key] = sanitize_evidence(child)
                continue
            if normalized in SENSITIVE_KEYS or normalized.endswith(SENSITIVE_SUFFIXES):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_evidence(child)
        return sanitized
    if isinstance(value, list):
        return [sanitize_evidence(child) for child in value]
    return copy.deepcopy(value)


def write_evidence_bundle(path: Path | str, evidence: dict[str, Any]) -> Path:
    """Write sanitized deterministic JSON plus a sibling SHA-256 manifest."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(sanitize_evidence(evidence), indent=2, sort_keys=True) + "\n"
    destination.write_text(payload)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    checksum_path = destination.with_name(destination.name + ".sha256")
    checksum_path.write_text(f"{checksum}  {destination.name}\n")
    return checksum_path
