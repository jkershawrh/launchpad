#!/usr/bin/env python3
"""Multimodal Image Pipeline — TDD Red Phase

Wire demo asset images to workload requests so the frontend
can display the image being processed alongside the AI output.
"""

import sys
import pytest


@pytest.fixture(autouse=True)
def setup(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")


class TestImageAssetMapping:

    def test_asset_map_exists(self):
        from overdrive.workload_generator import MULTIMODAL_DEMO_ASSETS
        assert isinstance(MULTIMODAL_DEMO_ASSETS, dict)

    def test_has_screenshot_assets(self):
        from overdrive.workload_generator import MULTIMODAL_DEMO_ASSETS
        assert "screenshot" in MULTIMODAL_DEMO_ASSETS
        assert len(MULTIMODAL_DEMO_ASSETS["screenshot"]) >= 2

    def test_has_diagram_assets(self):
        from overdrive.workload_generator import MULTIMODAL_DEMO_ASSETS
        assert "diagram" in MULTIMODAL_DEMO_ASSETS
        assert len(MULTIMODAL_DEMO_ASSETS["diagram"]) >= 1

    def test_has_image_assets(self):
        from overdrive.workload_generator import MULTIMODAL_DEMO_ASSETS
        assert "image" in MULTIMODAL_DEMO_ASSETS
        assert len(MULTIMODAL_DEMO_ASSETS["image"]) >= 2

    def test_assets_have_required_fields(self):
        from overdrive.workload_generator import MULTIMODAL_DEMO_ASSETS
        for modality, assets in MULTIMODAL_DEMO_ASSETS.items():
            for asset in assets:
                assert "url" in asset, f"{modality} asset missing url"
                assert "title" in asset, f"{modality} asset missing title"
                assert "description" in asset, f"{modality} asset missing description"


class TestGeneratorPopulatesAssets:

    def test_dashboard_storm_has_image_urls(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="dashboard_storm", mode="drive", seed=42)
        image_requests = [r for r in batch if r.image_count > 0]
        assert len(image_requests) > 0
        has_url = any(r.metadata.get("image_url") for r in image_requests)
        assert has_url, "Image requests should have image_url in metadata"

    def test_image_to_manual_has_image_urls(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="image_to_manual", mode="standby", seed=42)
        image_requests = [r for r in batch if r.modality == "image"]
        assert len(image_requests) > 0
        has_url = any(r.metadata.get("image_url") for r in image_requests)
        assert has_url

    def test_architecture_explainer_has_diagram_urls(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="architecture_explainer", mode="standby", seed=42)
        diagram_requests = [r for r in batch if r.modality == "diagram"]
        assert len(diagram_requests) > 0
        has_url = any(r.metadata.get("image_url") for r in diagram_requests)
        assert has_url


class TestStreamingResultsIncludeAssets:

    def test_results_have_image_url(self):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile="dashboard_storm", mode="standby", seed=42)
        has_url = any(r.get("image_url") for r in result.get("events", []))
        assert has_url, "Events should include image_url for visual requests"


class TestEndpointResponseIncludesAsset:

    def test_mock_response_includes_image_context(self):
        from overdrive.multimodal_endpoint import MockMultimodalEndpoint
        ep = MockMultimodalEndpoint(seed=42)
        r = ep.respond("screenshot_summary", "req-001", image_url="/demo-assets/dashboard-latency-spike.svg")
        assert "image_url" in r
        assert r["image_url"] == "/demo-assets/dashboard-latency-spike.svg"


class TestFrontendWiring:

    def test_workload_demo_has_image_display(self, project_root):
        content = (project_root / "frontend" / "src" / "pages" / "WorkloadDemo.tsx").read_text()
        assert "image_url" in content or "imageUrl" in content or "demo-assets" in content
