#!/usr/bin/env python3
"""Export a sanitized Launchpad pilot summary as a fail-closed VEF claim.

The exporter reads only the explicit input file. It does not import Launchpad,
contact a cluster, query the database, read environment variables, or alter labs.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "launchpad.vef-pilot-input.v1alpha1"
OUTPUT_SCHEMA = "launchpad.vef-pilot-claim.v1alpha1"
SENSITIVE_KEYS = {
    "content", "payload", "prompt", "response", "email", "participant_id",
    "labels", "namespace", "cluster", "credential", "credentials", "secret",
}


def _require(value: dict[str, Any], fields: tuple[str, ...], prefix: str = "") -> None:
    missing = [prefix + field for field in fields if field not in value]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))


def _number(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be a non-negative number")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be a non-negative number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return result


def _integer(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _reject_sensitive(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in SENSITIVE_KEYS:
                raise ValueError(f"sensitive or raw field is not accepted: {path}.{key}")
            _reject_sensitive(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive(child, f"{path}[{index}]")


def validate(data: dict[str, Any]) -> None:
    _reject_sensitive(data)
    _require(data, ("schema_version", "pilot_id", "period", "population", "baseline", "treatment", "safety", "ai_usage", "economics", "attribution", "approvals", "evidence_sources"))
    if data["schema_version"] != INPUT_SCHEMA:
        raise ValueError(f"schema_version must be {INPUT_SCHEMA}")
    if not isinstance(data["pilot_id"], str) or not data["pilot_id"].strip():
        raise ValueError("pilot_id must be a non-empty string")

    _require(data["period"], ("start", "end"), "period.")
    population = data["population"]
    _require(population, ("provisioned_seats", "enrolled_users", "active_users", "successful_journeys", "unknown_outcomes"), "population.")
    for field in ("provisioned_seats", "enrolled_users"):
        _integer(population[field], f"population.{field}", 1)
    for field in ("active_users", "successful_journeys", "unknown_outcomes"):
        _integer(population[field], f"population.{field}")
    if population["active_users"] > population["enrolled_users"]:
        raise ValueError("active_users cannot exceed enrolled_users")
    if population["enrolled_users"] > population["provisioned_seats"]:
        raise ValueError("enrolled_users cannot exceed provisioned_seats")

    for name in ("baseline", "treatment"):
        cohort = data[name]
        _require(cohort, ("method", "independent", "matched_population", "successful_journeys", "operating_cost_usd"), f"{name}.")
        if cohort["method"] not in {"matched_control", "historical_baseline", "unmeasured"}:
            raise ValueError(f"{name}.method is unknown")
        _integer(cohort["successful_journeys"], f"{name}.successful_journeys", 1)
        _number(cohort["operating_cost_usd"], f"{name}.operating_cost_usd")

    safety = data["safety"]
    _require(safety, ("accounting_complete", "failed_journeys", "probe_failures", "restart_increase", "cleanup_residue", "failure_threshold_breached"), "safety.")
    for field in ("failed_journeys", "probe_failures", "restart_increase", "cleanup_residue"):
        _integer(safety[field], f"safety.{field}")

    usage = data["ai_usage"]
    _require(usage, ("measurement_state", "actual_requests", "input_tokens", "output_tokens", "inference_cost_usd"), "ai_usage.")
    if usage["measurement_state"] not in {"unavailable", "partial", "authoritative"}:
        raise ValueError("ai_usage.measurement_state is unknown")
    for field in ("actual_requests", "input_tokens", "output_tokens", "inference_cost_usd"):
        if usage[field] is not None:
            _number(usage[field], f"ai_usage.{field}")

    economics = data["economics"]
    _require(economics, ("currency", "engineering_effort", "support_hours", "support_loaded_rate_usd", "other_realization_cost_usd", "marginal_delivery_cost_measured"), "economics.")
    if economics["currency"] != "USD":
        raise ValueError("economics.currency must be USD in v1alpha1")
    for field in ("support_hours", "support_loaded_rate_usd", "other_realization_cost_usd"):
        _number(economics[field], f"economics.{field}")
    if not isinstance(economics["engineering_effort"], list) or not economics["engineering_effort"]:
        raise ValueError("economics.engineering_effort must be a non-empty list")
    for index, effort in enumerate(economics["engineering_effort"]):
        prefix = f"economics.engineering_effort[{index}]."
        _require(effort, ("activity", "lifecycle", "role", "hours", "loaded_rate_usd", "source"), prefix)
        if effort["lifecycle"] not in {"initial", "recurring"}:
            raise ValueError(prefix + "lifecycle must be initial or recurring")
        _number(effort["hours"], prefix + "hours")
        _number(effort["loaded_rate_usd"], prefix + "loaded_rate_usd")

    share = _number(data["attribution"].get("product_share"), "attribution.product_share")
    if share > 1:
        raise ValueError("attribution.product_share must be between 0 and 1")
    factors = data["attribution"].get("competing_factors")
    if not isinstance(factors, list) or not factors:
        raise ValueError("attribution.competing_factors must be a non-empty list")
    _require(data["approvals"], ("manual_acceptance_complete", "security_triage_complete", "customer_validated", "finance_approved", "privacy_approved"), "approvals.")
    if not isinstance(data["evidence_sources"], list) or not data["evidence_sources"]:
        raise ValueError("evidence_sources must be a non-empty list")


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_export(data: dict[str, Any]) -> dict[str, Any]:
    validate(data)
    population = data["population"]
    baseline = data["baseline"]
    treatment = data["treatment"]
    safety = data["safety"]
    usage = data["ai_usage"]
    economics = data["economics"]
    approvals = data["approvals"]

    gaps: list[str] = []
    if population["unknown_outcomes"]:
        gaps.append("participant outcomes contain unknown states")
    if not baseline["independent"]:
        gaps.append("baseline is not independently observed")
    if not baseline["matched_population"]:
        gaps.append("baseline population is not matched")
    if baseline["method"] == "unmeasured":
        gaps.append("business counterfactual is unmeasured")
    if not safety["accounting_complete"]:
        gaps.append("outcome accounting is incomplete")
    if safety["failure_threshold_breached"]:
        gaps.append("preregistered safety threshold was breached")
    if safety["cleanup_residue"]:
        gaps.append("lab cleanup has residue")
    if usage["measurement_state"] != "authoritative":
        gaps.append("AI request, token, and inference cost evidence is not authoritative")
    if not economics["marginal_delivery_cost_measured"]:
        gaps.append("marginal delivery cost is not measured")
    for field in ("manual_acceptance_complete", "security_triage_complete", "customer_validated", "finance_approved", "privacy_approved"):
        if not approvals[field]:
            gaps.append(field.replace("_", " ") + " is missing")

    baseline_unit = _number(baseline["operating_cost_usd"], "baseline cost") / Decimal(baseline["successful_journeys"])
    treatment_unit = _number(treatment["operating_cost_usd"], "treatment cost") / Decimal(treatment["successful_journeys"])
    candidate_value = max(Decimal(0), (baseline_unit - treatment_unit) * Decimal(treatment["successful_journeys"]))

    effort_rows: list[dict[str, Any]] = []
    realization = _number(economics["other_realization_cost_usd"], "other realization cost")
    support_cost = _number(economics["support_hours"], "support hours") * _number(economics["support_loaded_rate_usd"], "support rate")
    realization += support_cost
    for effort in economics["engineering_effort"]:
        cost = _number(effort["hours"], "effort hours") * _number(effort["loaded_rate_usd"], "effort rate")
        realization += cost
        effort_rows.append({**effort, "cost_usd": _money(cost)})

    eligible = not gaps
    proof_state = "decision-grade" if eligible else ("directional" if baseline["method"] != "unmeasured" else "unproven")
    claim = {
        "id": f"launchpad.{data['pilot_id']}.cost-per-successful-journey",
        "product": "launchpad",
        "outcome_id": "launchpad.cost-per-slo-qualified-journey",
        "value_type": "cost_avoidance",
        "measurement": {
            "value_evidence_contract": "vef.claim.v1alpha1",
            "timestamp_start": data["period"]["start"],
            "timestamp_end": data["period"]["end"],
            "provisioned_seats": population["provisioned_seats"],
            "enrolled_users": population["enrolled_users"],
            "active_users": population["active_users"],
            "successful_journeys": population["successful_journeys"],
            "unknown": bool(population["unknown_outcomes"]),
            "baseline_cost_per_successful_journey_usd": _money(baseline_unit),
            "treatment_cost_per_successful_journey_usd": _money(treatment_unit),
            "observed_gross_value_candidate_usd": _money(candidate_value),
            "actual_ai_calls": usage["actual_requests"],
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "inference_cost_usd": usage["inference_cost_usd"],
            "quality_failures": {"dropped": safety["failed_journeys"], "false_negative": 0},
            "dangerous_misses": 1 if safety["failure_threshold_breached"] else 0,
            "safety": safety,
        },
        "counterfactual": {
            "method": "assertion" if baseline["method"] == "unmeasured" else baseline["method"],
            "expected_without_product": _money(baseline_unit),
        },
        "attribution": {"product_share": float(data["attribution"]["product_share"]), "competing_factors": sorted(data["attribution"]["competing_factors"])},
        "financial_model": {
            "gross_value": _money(candidate_value) if eligible else 0.0,
            "currency": "USD",
            "customer_validated": approvals["customer_validated"],
            "engineering_effort": effort_rows,
            "support_cost_usd": _money(support_cost),
        },
        "evidence": {"confidence": "high" if eligible else "unverified", "source": "sanitized_launchpad_pilot", "sources": sorted(data["evidence_sources"]), "reproducible": safety["accounting_complete"], "value_eligible": eligible},
        "realization_cost": _money(realization),
    }
    return {
        "schema_version": OUTPUT_SCHEMA,
        "proof_state": proof_state,
        "value_eligible": eligible,
        "eligibility_gaps": sorted(gaps),
        "claim": claim,
        "notice": "Launchpad readiness and lab performance are not proof of realized customer value.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_export(json.loads(args.input.read_text(encoding="utf-8")))
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"VEF pilot export failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
