#!/usr/bin/env python3
"""Stage 3: Workload Generator — TDD Red Phase"""

import sys
import pytest


@pytest.fixture(autouse=True)
def add_gateway_to_path(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


class TestDeterministicGeneration:

    def test_same_seed_same_output(self):
        from overdrive.workload_generator import generate_workload
        a = generate_workload(profile="incident_storm", mode="drive", seed=42)
        b = generate_workload(profile="incident_storm", mode="drive", seed=42)
        assert len(a) == len(b)
        for ra, rb in zip(a, b):
            assert ra.task_type == rb.task_type
            assert ra.token_estimate == rb.token_estimate
            assert ra.priority == rb.priority

    def test_different_seed_different_output(self):
        from overdrive.workload_generator import generate_workload
        a = generate_workload(profile="incident_storm", mode="drive", seed=42)
        b = generate_workload(profile="incident_storm", mode="drive", seed=99)
        types_a = [r.task_type for r in a]
        types_b = [r.task_type for r in b]
        assert types_a != types_b or [r.token_estimate for r in a] != [r.token_estimate for r in b]


class TestModeCount:

    def test_drive_generates_25(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="incident_storm", mode="drive", seed=1)
        assert len(batch) == 25

    def test_boost_generates_250(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="incident_storm", mode="boost", seed=1)
        assert len(batch) == 250

    def test_overdrive_generates_1000(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="incident_storm", mode="overdrive", seed=1)
        assert len(batch) == 1000

    def test_max_q_custom_count(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="incident_storm", mode="max_q", seed=1, count=5000)
        assert len(batch) == 5000


class TestRequestShape:

    def test_returns_inference_requests(self):
        from overdrive.workload_generator import generate_workload
        from overdrive.models import InferenceRequest
        batch = generate_workload(profile="incident_storm", mode="standby", seed=1)
        assert all(isinstance(r, InferenceRequest) for r in batch)

    def test_requests_have_ids(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="incident_storm", mode="standby", seed=1)
        ids = [r.request_id for r in batch]
        assert len(set(ids)) == len(ids), "Request IDs must be unique"

    def test_token_estimates_within_profile_range(self):
        from overdrive.workload_generator import generate_workload
        from overdrive.workload_profiles import PROFILES
        batch = generate_workload(profile="incident_storm", mode="drive", seed=42)
        profile = PROFILES["incident_storm"]
        ranges = {e["task_type"]: e["token_range"] for e in profile["task_mix"]}
        for r in batch:
            low, high = ranges[r.task_type]
            assert low <= r.token_estimate <= high, f"{r.task_type}: {r.token_estimate} not in [{low}, {high}]"

    def test_requests_have_latency_target(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="incident_storm", mode="standby", seed=1)
        assert all(r.latency_target_ms > 0 for r in batch)


class TestProfileMix:

    def test_incident_storm_has_expected_task_types(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="incident_storm", mode="boost", seed=42)
        types = {r.task_type for r in batch}
        assert "classification" in types
        assert "incident_rca" in types

    def test_rag_barrage_has_rag_question(self):
        from overdrive.workload_generator import generate_workload
        batch = generate_workload(profile="rag_barrage", mode="drive", seed=42)
        types = {r.task_type for r in batch}
        assert "rag_question" in types
        assert "embedding" in types
