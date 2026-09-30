from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_foundations_model_api_base_does_not_duplicate_openai_v1_path() -> None:
    catalog = yaml.safe_load(
        (REPO_ROOT / "catalog/virtualization-ai-foundations-101/catalog-item.yaml").read_text()
    )
    api_base = catalog["metadata"]["workload_helm_values"]["adapter"]["model"]["apiBase"]

    assert not api_base.rstrip("/").endswith("/v1")
