#!/usr/bin/env python3
"""Stage 3: Multimodal Workload Profiles — TDD Red Phase"""

import sys
import pytest


@pytest.fixture(autouse=True)
def setup(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


class TestMultimodalProfilesExist:

    def test_dashboard_storm_exists(self):
        from overdrive.workload_profiles import PROFILES
        assert "dashboard_storm" in PROFILES

    def test_multimodal_incident_commander_exists(self):
        from overdrive.workload_profiles import PROFILES
        assert "multimodal_incident_commander" in PROFILES

    def test_architecture_explainer_exists(self):
        from overdrive.workload_profiles import PROFILES
        assert "architecture_explainer" in PROFILES

    def test_visual_rag_barrage_exists(self):
        from overdrive.workload_profiles import PROFILES
        assert "visual_rag_barrage" in PROFILES

    def test_token_cannon_multimodal_exists(self):
        from overdrive.workload_profiles import PROFILES
        assert "token_cannon_multimodal" in PROFILES


class TestDashboardStorm:

    def test_has_screenshot_tasks(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["dashboard_storm"]["task_mix"]]
        assert "screenshot_classification" in types
        assert "screenshot_summary" in types

    def test_has_chart_interpretation(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["dashboard_storm"]["task_mix"]]
        assert "chart_interpretation" in types

    def test_has_modality_in_mix(self):
        from overdrive.workload_profiles import PROFILES
        for entry in PROFILES["dashboard_storm"]["task_mix"]:
            assert "modality" in entry


class TestTokenCannonMultimodal:

    def test_biases_gaudi(self):
        from overdrive.workload_profiles import PROFILES
        mix = PROFILES["token_cannon_multimodal"]["task_mix"]
        heavy = [e for e in mix if e["token_range"][0] >= 8000]
        total_weight = sum(e["weight"] for e in mix)
        heavy_weight = sum(e["weight"] for e in heavy)
        assert heavy_weight / total_weight >= 0.6


class TestVisualRagBarrage:

    def test_has_embedding_and_rag(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["visual_rag_barrage"]["task_mix"]]
        assert "image_text_embedding" in types
        assert "visual_rag_question" in types


class TestMultimodalGenerator:

    def test_generates_multimodal_requests(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="dashboard_storm", mode="standby", seed=42)
        assert len(batch) == 5
        has_multimodal = any(r.modality != "text" for r in batch)
        assert has_multimodal, "Dashboard storm should produce multimodal requests"

    def test_requests_have_image_ref(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="dashboard_storm", mode="drive", seed=42)
        image_requests = [r for r in batch if r.image_count > 0]
        assert len(image_requests) > 0

    def test_deterministic_multimodal(self):
        from overdrive.workload_generator import generate_workload
        a = generate_workload(profile="dashboard_storm", mode="drive", seed=42)
        b = generate_workload(profile="dashboard_storm", mode="drive", seed=42)
        for ra, rb in zip(a, b):
            assert ra.modality == rb.modality
            assert ra.image_count == rb.image_count
