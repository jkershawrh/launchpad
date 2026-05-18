#!/usr/bin/env python3
"""Stage 2: Workload Profiles — TDD Red Phase"""

import sys
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def add_gateway_to_path(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


class TestProfileDefinitions:

    def test_module_importable(self):
        from overdrive.workload_profiles import PROFILES
        assert isinstance(PROFILES, dict)

    def test_all_profiles_exist(self):
        from overdrive.workload_profiles import PROFILES
        expected = {"incident_storm", "rag_barrage", "token_cannon", "model_race",
                    "dashboard_storm", "multimodal_incident_commander", "architecture_explainer",
                    "visual_rag_barrage", "token_cannon_multimodal", "image_to_manual"}
        assert set(PROFILES.keys()) == expected

    def test_each_profile_has_task_mix(self):
        from overdrive.workload_profiles import PROFILES
        for name, profile in PROFILES.items():
            assert "task_mix" in profile, f"{name} missing task_mix"
            assert isinstance(profile["task_mix"], list)
            assert len(profile["task_mix"]) > 0

    def test_each_task_mix_entry_has_required_fields(self):
        from overdrive.workload_profiles import PROFILES
        for name, profile in PROFILES.items():
            for entry in profile["task_mix"]:
                assert "task_type" in entry, f"{name}: entry missing task_type"
                assert "weight" in entry, f"{name}: entry missing weight"
                assert "token_range" in entry, f"{name}: entry missing token_range"
                assert "priority" in entry, f"{name}: entry missing priority"

    def test_each_profile_has_description(self):
        from overdrive.workload_profiles import PROFILES
        for name, profile in PROFILES.items():
            assert "description" in profile, f"{name} missing description"

    def test_each_profile_has_expected_lane_bias(self):
        from overdrive.workload_profiles import PROFILES
        for name, profile in PROFILES.items():
            assert "expected_lane_bias" in profile, f"{name} missing expected_lane_bias"


class TestIncidentStorm:

    def test_contains_classification(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["incident_storm"]["task_mix"]]
        assert "classification" in types

    def test_contains_incident_rca(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["incident_storm"]["task_mix"]]
        assert "incident_rca" in types

    def test_contains_batch_summary(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["incident_storm"]["task_mix"]]
        assert "batch_summary" in types


class TestRagBarrage:

    def test_contains_embedding(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["rag_barrage"]["task_mix"]]
        assert "embedding" in types

    def test_contains_rerank(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["rag_barrage"]["task_mix"]]
        assert "rerank" in types

    def test_contains_rag_question(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["rag_barrage"]["task_mix"]]
        assert "rag_question" in types


class TestTokenCannon:

    def test_biases_heavy_generation(self):
        from overdrive.workload_profiles import PROFILES
        mix = PROFILES["token_cannon"]["task_mix"]
        heavy = [e for e in mix if e["token_range"][0] >= 16000]
        total_weight = sum(e["weight"] for e in mix)
        heavy_weight = sum(e["weight"] for e in heavy)
        assert heavy_weight / total_weight >= 0.6, "Token cannon should bias >60% toward heavy generation"


class TestModelRace:

    def test_generates_comparable_batch(self):
        from overdrive.workload_profiles import PROFILES
        types = [e["task_type"] for e in PROFILES["model_race"]["task_mix"]]
        assert "classification" in types
        assert "short_summary" in types
        assert "long_summary" in types


class TestListProfiles:

    def test_list_profiles(self):
        from overdrive.workload_profiles import list_profiles
        profiles = list_profiles()
        assert len(profiles) == 10
        assert all("name" in p and "description" in p for p in profiles)
