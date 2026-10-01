from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/intel-xeon6-agent-201/catalog-item.yaml"
OVERLAY = (
    ROOT
    / "deploy/launchpad/overlays/flightpath-candidate/intel-xeon6-agent-201.catalog-item.yaml"
)


def test_flightpath_overlay_uses_the_reviewed_immutable_agent_201_contract():
    catalog = yaml.safe_load(CATALOG.read_text())
    overlay = yaml.safe_load(OVERLAY.read_text())

    assert overlay["version"] == catalog["version"]
    assert overlay["status"] == "active"

    expected_metadata = catalog["metadata"]
    actual_metadata = overlay["metadata"]
    for key in (
        "certification_stage",
        "max_workshop_seats",
        "showroom_content_repo_url",
        "showroom_content_ref",
        "showroom_content_playbook",
        "showroom_content_start_path",
        "source_content_repo",
        "source_content_revision",
        "workload_repo",
        "workload_revision",
        "workload_routes",
        "showroom_tabs",
        "activation_blockers",
    ):
        assert actual_metadata[key] == expected_metadata[key]


def test_agent_201_is_orderable_only_at_its_certified_one_seat_limit():
    overlay = yaml.safe_load(OVERLAY.read_text())

    assert overlay["status"] == "active"
    assert overlay["metadata"]["max_workshop_seats"] == 1
    assert overlay["metadata"]["certification_stage"] == "1-seat-certified"
    assert overlay["metadata"]["activation_blockers"] == []
