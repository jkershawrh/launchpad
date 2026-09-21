from __future__ import annotations

from pathlib import Path

import yaml

from app.services.catalog_onboarding import (
    build_catalog_item,
    discover_quickstart_quality,
    discover_quickstart_repo,
)


def _quality_source(root: Path) -> Path:
    source = root / "quickstart"
    pages = source / "showroom/modules/ROOT/pages"
    pages.mkdir(parents=True)
    (source / "README.md").write_text(
        """# Build a Support Assistant

Help support teams classify customer requests and reduce response time.

## Table of Contents
## Overview
## Architecture
## Requirements
## Deploy
## Repository structure
## References
## Tags
""",
        encoding="utf-8",
    )
    (source / "site.yml").write_text(
        "content:\n  sources:\n    - url: .\n      start_path: showroom\n",
        encoding="utf-8",
    )
    (source / "showroom/antora.yml").write_text(
        "name: support-assistant\ntitle: Support Assistant\nversion: ~\n",
        encoding="utf-8",
    )
    (pages / "index.adoc").write_text("= Welcome\n", encoding="utf-8")
    module = [
        "= Classify a customer request",
        "",
        "You are a support engineer deciding how to route an urgent request.",
        "",
        "== What you will learn",
        "",
        "* Explain the request-routing workflow",
        "* Run and verify the classifier",
        "",
        "== See: Request routing",
        "",
        "The API sends the request to a shared model endpoint.",
        "The response is normalized before it reaches the queue.",
        "The routing decision remains visible to the participant.",
        "The model is separate from the business policy.",
        "",
        "== Do: Run the workflow",
        "",
        "The following command verifies the application health endpoint.",
        "",
        '[source,bash,role="execute",subs="attributes+"]',
        "----",
        "curl -fsS http://support-api:8080/health",
        "----",
        "",
        "=== Verify",
        "",
        "Confirm the response reports healthy.",
        "",
        "== Key takeaway",
        "",
        "You separated model inference from deterministic routing policy.",
    ]
    module.extend(f"Supporting explanation line {index}." for index in range(55))
    (pages / "01-classify.adoc").write_text(
        "\n".join(module) + "\n", encoding="utf-8"
    )
    tests = source / "tests"
    (tests / "publication").mkdir(parents=True)
    (tests / "validation_matrix.yaml").write_text(
        "stages:\n  - id: stage_1_contract\n  - id: stage_2_unit\n",
        encoding="utf-8",
    )
    (tests / "claim_registry.yaml").write_text(
        "claims:\n  - id: response-time\n    verified: false\n",
        encoding="utf-8",
    )
    (tests / "benchmark_rubric.yaml").write_text(
        "benchmarks:\n  - id: response-time\n    max_ms: 5000\n",
        encoding="utf-8",
    )
    (tests / "publication/test_readme.py").write_text(
        "def test_readme():\n    assert True\n", encoding="utf-8"
    )
    (source / "Makefile").write_text("test-all:\n\tpytest -q\n", encoding="utf-8")
    workflows = source / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yaml").write_text("name: ci\n", encoding="utf-8")
    app = source / "src"
    app.mkdir()
    (app / "client.py").write_text(
        'OPENAI_API_BASE = "https://model.example.test/v1"\n', encoding="utf-8"
    )
    chart = source / "deploy/chart"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: support-assistant\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    (chart / "values.yaml").write_text("{}\n", encoding="utf-8")
    return source


def test_quality_profile_reuses_quickstart_authoring_and_showroom_signals(
    tmp_path: Path,
) -> None:
    source = _quality_source(tmp_path)

    quality = discover_quickstart_quality(source, inventory={
        "mutable_images": [],
        "cluster_scoped_resources": [],
        "privileged_findings": [],
        "secret_manifests": [],
        "unparsed_manifests": [],
        "resource_envelopes": [],
        "models": [],
    })

    assert quality["schema_version"] == "launchpad.redhat.com/catalog-intake-quality/v1"
    assert quality["business_solution"]["readme_present"] is True
    assert quality["business_solution"]["action_oriented_title"] is True
    assert quality["business_solution"]["required_sections_present"] is True
    assert quality["artifacts"]["validation_matrix"]["status"] == "present-valid"
    assert quality["artifacts"]["claim_registry"]["entry_count"] == 1
    assert quality["artifacts"]["benchmark_rubric"]["entry_count"] == 1
    assert quality["showroom"]["hands_on_module_count"] == 1
    assert quality["showroom"]["execute_block_count"] == 1
    assert quality["showroom"]["thin_modules"] == []
    assert quality["capacity_proposal"]["inference_mode"] == "remote-endpoint"
    assert quality["capacity_proposal"]["status"] == "review-required"
    assert quality["portfolio_overlap"]["status"] == "not-run"
    assert quality["authority"]["may_modify_source"] is False
    assert quality["authority"]["may_publish_catalog"] is False


def test_repository_discovery_blocks_missing_quickstart_quality_artifacts(
    tmp_path: Path,
) -> None:
    source = _quality_source(tmp_path)
    (source / "tests/claim_registry.yaml").unlink()

    intake, report = discover_quickstart_repo(
        source,
        repo_url="https://github.com/example/support-assistant.git",
        revision="a" * 40,
        catalog_id="support-assistant",
        display_name="Support Assistant",
    )

    assert report["discovery_status"] == "pass"
    assert intake["quality"]["artifacts"]["claim_registry"]["status"] == "missing"
    assert intake["quality"]["gate"]["status"] == "blocked"
    assert any(
        "Quickstart quality" in blocker
        for blocker in intake["certification"]["activation_blockers"]
    )
    catalog = build_catalog_item(intake)
    assert (
        catalog["metadata"]["intake_quality"]["gate"]["status"]
        == "blocked"
    )


def test_quality_contract_keeps_rhdp_delivery_and_live_mutation_outside_scope() -> None:
    root = Path(__file__).resolve().parents[2]
    contract = yaml.safe_load(
        (root / "contracts/catalog-intake-quality-v1.yaml").read_text(encoding="utf-8")
    )

    assert contract["authority"]["mode"] == "analysis-only"
    assert contract["authority"]["may_modify_source"] is False
    assert contract["authority"]["may_publish_catalog"] is False
    assert contract["outputs"]["agnosticv"] is False
    assert contract["outputs"]["agnosticd"] is False
    assert contract["execution"]["untrusted_source_runs_on_host"] is False
    assert contract["portfolio_overlap"]["mutable_live_org_scan_allowed"] is False
