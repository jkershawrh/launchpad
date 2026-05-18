#!/usr/bin/env python3
"""Demo Validation — Gate-Staged TDD

Each gate must pass before proceeding to the next.
Gate 6 (live cluster smoke) is manual — run with LIVE_TEST=1.
"""

import os
import sys
import pytest


@pytest.fixture(autouse=True)
def setup(project_root, monkeypatch):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)
    monkeypatch.setenv("LITELLM_API_BASE", "https://litellm-test.example.com")
    monkeypatch.setenv("WORKLOAD_UNLOCK_HASH", "")


# ----------------------------------------------------------------
# GATE 1: Rate Limit Alignment
# ----------------------------------------------------------------

class TestGate1RateLimits:

    def test_gateway_rpm_at_or_below_litellm_limit(self):
        from router import RATE_LIMIT_RPM
        assert RATE_LIMIT_RPM <= 90, f"Gateway RPM ({RATE_LIMIT_RPM}) must not exceed LiteLLM limit (90)"

    def test_real_timing_provider_throttle_below_limit(self):
        from overdrive.timing_provider import RealTimingProvider
        tp = RealTimingProvider(gateway_url="http://localhost:8080")
        effective_rpm = 60000 / tp.min_interval_ms
        assert effective_rpm <= 90, f"RealTimingProvider effective RPM ({effective_rpm:.0f}) exceeds LiteLLM limit"


# ----------------------------------------------------------------
# GATE 2: Task-to-Model Mapping Complete
# ----------------------------------------------------------------

class TestGate2TaskModelMapping:

    def test_all_text_tasks_mapped(self):
        from overdrive.timing_provider import TASK_TO_LITELLM_MODEL
        text_tasks = ["classification", "embedding", "rerank", "short_summary", "long_summary",
                      "incident_rca", "batch_summary", "rag_question", "document_summary", "code_summary"]
        for task in text_tasks:
            assert task in TASK_TO_LITELLM_MODEL, f"Text task '{task}' not in TASK_TO_LITELLM_MODEL"

    def test_all_multimodal_tasks_mapped(self):
        from overdrive.timing_provider import TASK_TO_LITELLM_MODEL
        mm_tasks = ["image_classification", "screenshot_classification", "image_text_embedding",
                     "visual_similarity", "ocr_layout_extract", "screenshot_summary",
                     "chart_interpretation", "diagram_explanation", "document_visual_summary",
                     "visual_rag_question", "multimodal_incident_summary", "multimodal_rca",
                     "image_to_manual"]
        for task in mm_tasks:
            assert task in TASK_TO_LITELLM_MODEL, f"Multimodal task '{task}' not in TASK_TO_LITELLM_MODEL"

    def test_eco_tasks_map_to_small_model(self):
        from overdrive.timing_provider import TASK_TO_LITELLM_MODEL
        eco_tasks = ["classification", "image_classification", "screenshot_classification"]
        for task in eco_tasks:
            model = TASK_TO_LITELLM_MODEL[task]
            assert "granite" in model or "tiny" in model.lower(), f"Eco task '{task}' should map to small model, got '{model}'"

    def test_overdrive_tasks_map_to_large_model(self):
        from overdrive.timing_provider import TASK_TO_LITELLM_MODEL
        od_tasks = ["screenshot_summary", "chart_interpretation", "diagram_explanation",
                    "multimodal_incident_summary", "multimodal_rca", "image_to_manual"]
        for task in od_tasks:
            model = TASK_TO_LITELLM_MODEL[task]
            assert "scout" in model or "llama" in model.lower(), f"Overdrive task '{task}' should map to large model, got '{model}'"


# ----------------------------------------------------------------
# GATE 3: RealTimingProvider Accepts Multimodal Params
# ----------------------------------------------------------------

class TestGate3RealProviderParams:

    def test_accepts_modality_kwarg(self):
        from overdrive.timing_provider import RealTimingProvider
        tp = RealTimingProvider(gateway_url="http://localhost:8080")
        import inspect
        sig = inspect.signature(tp.simulate)
        assert "modality" in sig.parameters, "RealTimingProvider.simulate() must accept modality"

    def test_accepts_image_count_kwarg(self):
        from overdrive.timing_provider import RealTimingProvider
        import inspect
        sig = inspect.signature(RealTimingProvider.simulate)
        assert "image_count" in sig.parameters

    def test_accepts_page_count_kwarg(self):
        from overdrive.timing_provider import RealTimingProvider
        import inspect
        sig = inspect.signature(RealTimingProvider.simulate)
        assert "page_count" in sig.parameters


# ----------------------------------------------------------------
# GATE 4: Profile-Routing Consistency
# ----------------------------------------------------------------

class TestGate4ProfileRoutingConsistency:

    def test_all_profile_tasks_have_routing_rules(self):
        from overdrive.workload_profiles import PROFILES
        from overdrive.matrix import load_config
        from pathlib import Path
        config = load_config(Path(__file__).parent.parent / "gateway" / "overdrive" / "config.yaml")
        matrix_tasks = {r["task_type"] for r in config["routing_matrix"]}

        missing = []
        for name, profile in PROFILES.items():
            for entry in profile["task_mix"]:
                if entry["task_type"] not in matrix_tasks:
                    missing.append(f"{name}/{entry['task_type']}")
        assert not missing, f"Profile task types with no routing rule: {missing}"

    def test_all_profile_tasks_have_lane_capability(self):
        from overdrive.workload_profiles import PROFILES
        from overdrive.matrix import load_config
        from pathlib import Path
        config = load_config(Path(__file__).parent.parent / "gateway" / "overdrive" / "config.yaml")

        all_caps = set()
        for lane in config["lanes"].values():
            all_caps.update(lane.get("capabilities", []))

        missing = []
        for name, profile in PROFILES.items():
            for entry in profile["task_mix"]:
                if entry["task_type"] not in all_caps:
                    missing.append(f"{name}/{entry['task_type']}")
        assert not missing, f"Profile task types not in any lane capabilities: {missing}"

    def test_all_profiles_have_prompts_for_tasks(self):
        from overdrive.workload_profiles import PROFILES
        missing = []
        for name, profile in PROFILES.items():
            prompts = profile.get("prompts", {})
            for entry in profile["task_mix"]:
                if entry["task_type"] not in prompts or not prompts[entry["task_type"]]:
                    missing.append(f"{name}/{entry['task_type']}")
        assert not missing, f"Profile tasks with no prompts: {missing}"

    def test_mock_endpoint_covers_all_multimodal_tasks(self):
        from overdrive.multimodal_endpoint import MOCK_RESPONSES
        from overdrive.workload_profiles import PROFILES
        mm_tasks = set()
        for profile in PROFILES.values():
            for entry in profile["task_mix"]:
                if entry.get("modality", "text") != "text":
                    mm_tasks.add(entry["task_type"])
        missing = [t for t in mm_tasks if t not in MOCK_RESPONSES]
        assert not missing, f"Multimodal tasks with no mock response: {missing}"


# ----------------------------------------------------------------
# GATE 5: Simulated E2E for Every Profile
# ----------------------------------------------------------------

class TestGate5AllProfilesRun:

    @pytest.fixture(params=[
        "incident_storm", "rag_barrage", "token_cannon", "model_race",
        "dashboard_storm", "multimodal_incident_commander", "architecture_explainer",
        "visual_rag_barrage", "token_cannon_multimodal", "image_to_manual",
    ])
    def profile(self, request):
        return request.param

    def test_profile_completes_standby(self, profile):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile=profile, mode="standby", seed=42)
        assert result["completed_requests"] == 5, f"{profile} did not complete 5 requests"
        assert result["failed_requests"] == 0

    def test_profile_has_route_distribution(self, profile):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile=profile, mode="standby", seed=42)
        assert sum(result["route_counts"].values()) == 5

    def test_profile_generates_report(self, profile):
        from overdrive.batch_runner import run_workload
        result = run_workload(profile=profile, mode="standby", seed=42)
        assert len(result.get("report_md", "")) > 100
        assert len(result.get("report_json", "")) > 50
