import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog/network-operations-agent/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/network-operations-agent.yaml"
CERTIFICATION = ROOT / "certification/catalog/network-operations-agent.yaml"
EVIDENCE = (
    ROOT
    / "evidence/runs/flightpath-live-20261002-network-operations-agent-public-1seat-r1.json"
)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_active_network_operations_experience_transfers_exact_certified_release() -> None:
    catalog = _yaml(CATALOG)
    intake = _yaml(INTAKE)
    contract = _yaml(CERTIFICATION)
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    metadata = catalog["metadata"]
    revision = "6ed5c53337afa55c03949b2963b429f32977ef69"
    image_digest = (
        "sha256:a6ac58c4040127bdd790a2f2fd61c9eacf659f346d6c70d5da5dec06e7756242"
    )

    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert metadata["certification_stage"] == intake["certification"]["stage"] == (
        "1-seat-certified"
    )
    assert intake["certification"]["certified_seats"] == 1
    assert metadata["max_workshop_seats"] == intake["certification"][
        "max_workshop_seats"
    ] == 1
    assert metadata["public_access_certification_stage"] == "one-seat-certified"
    assert metadata["public_max_workshop_seats"] == 1
    assert metadata["allowed_exposure_policies"] == intake["runtime"][
        "allowed_exposure_policies"
    ] == ["internal", "public_code"]

    assert metadata["showroom_content_ref"] == metadata["workload_revision"] == revision
    assert metadata["source_content_revision"] == revision
    for source in intake["sources"].values():
        assert source["revision"] == revision
        assert source["repo_url"] == (
            "https://github.com/jkershawrh/network-operations-agent.git"
        )
        assert source["gitops_repo_url"] == source["repo_url"]
    assert intake["runtime"]["workload"]["helm_values"]["image"]["digest"] == (
        image_digest
    )

    assert intake["runtime"]["tabs"] == metadata["showroom_tabs"]
    assert [tab["id"] for tab in metadata["showroom_tabs"]] == [
        "story",
        "terminal",
        "workspace",
        "openshift-console",
    ]
    story, _, workspace, _ = metadata["showroom_tabs"]
    assert story["same_origin_path"] == "/story/"
    assert story["public_proxy_root"] is True
    assert workspace["same_origin_path"] == "/workspace"
    assert workspace["rewrite_target"] == "/"
    assert [path["path"] for path in workspace["proxy_paths"]] == ["/api", "/health"]

    assert metadata["required_models"] == intake["runtime"]["required_models"] == [
        "granite-3.2-8b-tools"
    ]
    assert metadata["inference_endpoint"] == intake["runtime"][
        "inference_endpoint"
    ] == "litellm_virtual_key_candidate"
    assert metadata["workload_runtime_secret_sources"] == intake["runtime"][
        "workload"
    ]["runtime_secret_sources"]

    references = metadata["source_references"]
    assert references["release_workflow"] == (
        "https://github.com/jkershawrh/network-operations-agent/actions/runs/36733546281"
    )
    assert references["certification_evidence"] == str(EVIDENCE.relative_to(ROOT))

    expected_hash = EVIDENCE.with_suffix(".json.sha256").read_text().split()[0]
    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected_hash
    assert evidence["contract"]["sha256"] == hashlib.sha256(
        CERTIFICATION.read_bytes()
    ).hexdigest()
    assert evidence["result"] == "GREEN-live"
    assert evidence["rubric"]["score"] == 100
    result = evidence["seat_results"][0]["probe"]["result"]
    assert result["readiness"] == {
        "health": True,
        "mcp_ready": True,
        "story_http_status": 200,
        "workspace_http_status": 200,
    }
    assert result["investigation"] == {
        "action_executed": False,
        "cause": "hardware_timing",
        "human_approval": True,
        "live_model": True,
        "model": "granite-3.2-8b-tools",
    }
    assert result["qualification"]["result"] == "pass"
    assert result["qualification"]["scenarios"] == 5
    assert evidence["security"]["contains_plaintext_credentials"] is False
    assert evidence["cleanup"]["model_keys_revoked"] is True
    assert evidence["cleanup"]["status"] == "completed"
    assert all(count == 0 for count in evidence["cleanup"]["resource_counts"].values())


def test_intake_quality_remains_non_authoritative_after_live_certification() -> None:
    catalog = _yaml(CATALOG)
    intake = _yaml(INTAKE)

    # Static intake is intentionally fail-closed and cannot grant promotion. The
    # immutable certification contract and evidence above are the authority for
    # the independently recorded one-seat promotion.
    assert catalog["metadata"]["intake_quality"] == intake["quality"]
    assert intake["quality"]["authority"] == {
        "mode": "analysis-only",
        "may_modify_source": False,
        "may_publish_catalog": False,
        "may_provision": False,
        "may_certify": False,
    }
