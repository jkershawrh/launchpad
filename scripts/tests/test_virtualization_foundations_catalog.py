from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_foundations_model_api_base_does_not_duplicate_openai_v1_path() -> None:
    catalog = yaml.safe_load(
        (REPO_ROOT / "catalog/virtualization-ai-foundations-101/catalog-item.yaml").read_text()
    )
    api_base = catalog["metadata"]["workload_helm_values"]["adapter"]["model"]["apiBase"]

    assert not api_base.rstrip("/").endswith("/v1")


def test_foundations_certification_requires_the_observed_live_advisory() -> None:
    contract = yaml.safe_load(
        (REPO_ROOT / "certification/catalog/virtualization-ai-foundations-101.yaml").read_text()
    )
    assertions = contract["spec"]["seat_probe"]["json_assertions"]

    assert {"path": "journey.source_state", "equals": "LIVE"} in assertions


def test_virtualization_301_uses_flightpath_capability_names() -> None:
    catalog = yaml.safe_load(
        (REPO_ROOT / "catalog/virtualization-ai-301/catalog-item.yaml").read_text()
    )

    assert catalog["required_capabilities"] == [
        "openshift",
        "openshift-virtualization",
        "showroom",
    ]
