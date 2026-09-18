from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate_product_roadmap_dashboard.py"


def load_module():
    spec = importlib.util.spec_from_file_location("roadmap_dashboard", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_roadmap_preserves_hierarchy_and_all_tasks():
    module = load_module()
    model = module.parse_roadmap(ROOT / "docs" / "product-delivery-roadmap.md")

    assert len(model["horizons"]) == 5
    assert len(model["epics"]) == 29
    assert len(model["stories"]) == 35
    assert len(model["tasks"]) == 182
    assert "LP-T095" in model["tasks"]
    assert "lab.step.executed" in model["tasks"]["LP-T095"]["title"]
    assert model["tasks"]["LP-T084"]["epic_id"] == "LP-E002"
    assert model["tasks"]["LP-T094"]["story_id"] == "LP-S024"
    assert model["tasks"]["LP-T101"]["epic_id"] == "LP-E019"
    assert model["tasks"]["LP-T107"]["epic_id"] == "LP-E020"
    assert model["tasks"]["LP-T113"]["epic_id"] == "LP-E021"
    assert model["tasks"]["LP-T119"]["epic_id"] == "LP-E022"
    assert model["tasks"]["LP-T127"]["epic_id"] == "LP-E023"
    assert model["tasks"]["LP-T135"]["epic_id"] == "LP-E024"
    assert model["tasks"]["LP-T143"]["epic_id"] == "LP-E025"
    assert model["tasks"]["LP-T153"]["epic_id"] == "LP-E026"
    assert model["tasks"]["LP-T162"]["epic_id"] == "LP-E027"
    assert model["tasks"]["LP-T172"]["epic_id"] == "LP-E028"
    assert model["tasks"]["LP-T181"]["epic_id"] == "LP-E029"
    assert model["tasks"]["LP-T182"]["epic_id"] == "LP-E021"


def test_status_rollup_requires_all_five_proof_methods(tmp_path: Path):
    module = load_module()
    status_path = tmp_path / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tasks": {
                    "LP-T001": {
                        "state": "green-live",
                        "methods": {
                            "tdd": "green-live",
                            "edd": "green-live",
                            "cdd": "green-live",
                            "bdd": "green-live",
                            "cbt": "red",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status = module.load_status(status_path)
    task = module.normalise_task_status("LP-T001", status)

    assert task["state"] == "red"
    assert task["declared_state"] == "green-live"
    assert task["proof_complete"] is False


def test_render_is_self_contained_and_exposes_required_views():
    module = load_module()
    model = module.parse_roadmap(ROOT / "docs" / "product-delivery-roadmap.md")
    status = module.load_status(ROOT / "docs" / "product-roadmap-status.json")
    html = module.render_dashboard(model, status, ROOT)

    assert 'data-view="gantt"' in html
    assert 'data-view="matrix"' in html
    assert 'data-view="pilot"' in html
    assert "September 17 Pilot" in html
    assert "191" in html and "79" in html and "270" in html
    assert "Participant completion was not consistently instrumented" in html
    assert "Participant journey correlation" in html
    assert '"unique_participant_identities": 67' in html
    assert '"all_three_catalogs": 47' in html
    assert '"participants_reentering_same_workshop": 12' in html
    assert "PII excluded" in html
    assert "Financial readiness" in html
    assert "$20K–$55K" in html
    assert "$23K–$40K" in html
    assert "160 hours" in html
    assert '"minimum_known_vcpu_hours": 100666' in html
    assert "Conventional replacement" in html
    assert "TDD" in html and "EDD" in html and "CDD" in html
    assert "BDD" in html and "CBT" in html
    assert "Release rubric" in html
    assert "LP-T094" in html
    assert "LP-T008" in html
    assert "five digest-pinned images" in html
    assert "lab.step.started" in html
    assert "lab.step.executed" in html
    assert "lab.checkpoint.completed" in html
    assert "Automated lab intake and certification" in html
    assert "Capacity engineering, forecasting, and admission" in html
    assert "Control-plane portability and production-home promotion" in html
    assert "Parallel convergence and earned promotion" in html
    assert "Organizational readiness and knowledge continuity" in html
    assert "Governed open-source distribution" in html
    assert "Governed AI control plane and gateway" in html
    assert "On receipt of the permanent-home environment" in html
    assert "Launchpad Knowledge Assistant" in html
    assert "OSS-to-enterprise" in html
    assert f"Filter the {len(model['tasks'])} tasks" in html
    assert "Filter the 94 tasks" not in html
    assert "<svg" in html
    assert "Red Hat" in html and "Intel" in html
    assert 'viewBox="0 0 192.30001 146"' in html
    assert 'font-size="72"' not in html
    assert "fetch(" not in html


def test_admin_navigation_exposes_the_generated_roadmap():
    layout = (ROOT / "admin" / "src" / "components" / "AdminLayout.tsx").read_text(
        encoding="utf-8"
    )
    admin_roadmap = ROOT / "admin" / "public" / "roadmap" / "index.html"

    assert "{ path: '/roadmap/', label: 'Roadmap', document: true }" in layout
    assert admin_roadmap.exists()
    assert admin_roadmap.read_text(encoding="utf-8") == (
        ROOT / "docs" / "product-roadmap-dashboard.html"
    ).read_text(encoding="utf-8")


def test_release_rubric_is_complete_and_balanced():
    module = load_module()
    status = module.load_status(ROOT / "docs" / "product-roadmap-status.json")
    rubric = status["rubric"]

    assert sum(item["weight"] for item in rubric) == 100
    assert {item["id"] for item in rubric} >= {
        "production-quality",
        "sre-operations",
        "security-governance",
        "gtm-customer-success",
        "organizational-readiness",
        "oss-readiness",
    }
