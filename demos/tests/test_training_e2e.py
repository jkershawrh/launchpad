#!/usr/bin/env python3
"""Training Demo — TDD tests (all stages)

Everything is SIMULATED. No actual training occurs.
"""

import sys
import json
import pytest


@pytest.fixture(autouse=True)
def setup(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


# --- Stage 1: Models ---

class TestModelProfiles:

    def test_all_profiles_exist(self):
        from overdrive.training_models import MODEL_PROFILES
        expected = {"qwen_2_5_7b", "qwen_2_5_coder_7b", "qwen_2_5_vl_7b", "llama_3_1_8b", "granite_ops_model", "phi_small_utility"}
        assert set(MODEL_PROFILES.keys()) == expected

    def test_each_profile_has_required_fields(self):
        from overdrive.training_models import MODEL_PROFILES
        for name, p in MODEL_PROFILES.items():
            assert "family" in p, f"{name} missing family"
            assert "name" in p, f"{name} missing name"
            assert "params_b" in p, f"{name} missing params_b"
            assert "training_lane" in p, f"{name} missing training_lane"
            assert "serving_lane" in p, f"{name} missing serving_lane"

    def test_list_model_profiles(self):
        from overdrive.training_models import list_model_profiles
        profiles = list_model_profiles()
        assert len(profiles) == 6
        assert all("id" in p for p in profiles)


class TestDatasetProfiles:

    def test_all_datasets_exist(self):
        from overdrive.training_models import DATASET_PROFILES
        assert len(DATASET_PROFILES) == 5
        assert "synthetic_incident_rca_v1" in DATASET_PROFILES
        assert "synthetic_dashboard_vision_v1" in DATASET_PROFILES

    def test_each_dataset_has_required_fields(self):
        from overdrive.training_models import DATASET_PROFILES
        for name, d in DATASET_PROFILES.items():
            assert "task_type" in d, f"{name} missing task_type"
            assert "sample_count" in d, f"{name} missing sample_count"
            assert "train_count" in d
            assert "eval_count" in d
            assert d["synthetic"] is True, f"{name} must be synthetic in this phase"


class TestTrainingRunModel:

    def test_create_training_run(self):
        from overdrive.training_models import TrainingRun
        run = TrainingRun(
            training_run_id="test-001", demo_task="incident_rca_finetune",
            model_profile_id="qwen_2_5_7b", base_model_name="Qwen2.5-7B",
            dataset_id="synthetic_incident_rca_v1",
        )
        assert run.status == "created"
        assert run.training_mode == "mock_lora"

    def test_training_run_rejects_nothing(self):
        from overdrive.training_models import TrainingRun
        run = TrainingRun(training_run_id="x", demo_task="x", model_profile_id="x",
                          base_model_name="x", dataset_id="x")
        assert run is not None


class TestTrainingTasks:

    def test_all_tasks_exist(self):
        from overdrive.training_models import TRAINING_TASKS
        expected = {"incident_rca_finetune", "openshift_troubleshooting_finetune",
                    "dashboard_vision_finetune", "code_failure_finetune", "small_classifier_tune"}
        assert set(TRAINING_TASKS.keys()) == expected


# --- Stage 2: Mock Training Backend ---

class TestMockTrainingBackend:

    def test_run_completes(self):
        from overdrive.training_backend import MockTrainingBackend
        backend = MockTrainingBackend(seed=42)
        run = backend.run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        assert run.status == "completed"

    def test_deterministic_by_seed(self):
        from overdrive.training_backend import MockTrainingBackend
        a = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        b = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        assert a.metrics["train_loss_start"] == b.metrics["train_loss_start"]
        assert a.evaluation["base_score"] == b.evaluation["base_score"]

    def test_generates_loss_curve(self):
        from overdrive.training_backend import MockTrainingBackend
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        assert len(run.loss_curve) == 20
        assert run.loss_curve[0] > run.loss_curve[-1]

    def test_marks_as_simulated(self):
        from overdrive.training_backend import MockTrainingBackend
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        assert run.metrics["simulated"] is True
        assert run.metadata["simulated"] is True

    def test_generates_artifact_refs(self):
        from overdrive.training_backend import MockTrainingBackend
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        assert "adapter_ref" in run.artifacts
        assert "model_card_ref" in run.artifacts

    def test_evaluation_has_improvement(self):
        from overdrive.training_backend import MockTrainingBackend
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        assert run.evaluation["tuned_score"] > run.evaluation["base_score"]
        assert run.evaluation["improvement"] > 0

    def test_evaluation_has_dimensions(self):
        from overdrive.training_backend import MockTrainingBackend
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        dims = run.evaluation["dimensions"]
        assert "format" in dims
        assert "relevance" in dims
        assert "technical_specificity" in dims

    def test_rejects_unknown_model(self):
        from overdrive.training_backend import MockTrainingBackend
        with pytest.raises(ValueError):
            MockTrainingBackend().run("incident_rca_finetune", "nonexistent", "synthetic_incident_rca_v1")

    def test_rejects_unknown_dataset(self):
        from overdrive.training_backend import MockTrainingBackend
        with pytest.raises(ValueError):
            MockTrainingBackend().run("incident_rca_finetune", "qwen_2_5_7b", "nonexistent")


# --- Stage 3: Serving Candidate ---

class TestServingCandidate:

    def test_created_after_training(self):
        from overdrive.training_backend import MockTrainingBackend
        backend = MockTrainingBackend(seed=42)
        run = backend.run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        candidate = backend.create_serving_candidate(run)
        assert candidate.status == "simulated_ready"
        assert candidate.training_run_id == run.training_run_id
        assert candidate.target_lane == "gaudi_overdrive"

    def test_has_artifact_ref(self):
        from overdrive.training_backend import MockTrainingBackend
        backend = MockTrainingBackend(seed=42)
        run = backend.run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        candidate = backend.create_serving_candidate(run)
        assert candidate.artifact_ref != ""


# --- Stage 5: Reports ---

class TestTrainingReports:

    def test_json_report(self):
        from overdrive.training_backend import MockTrainingBackend
        from overdrive.training_report import generate_training_json
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        j = generate_training_json(run)
        parsed = json.loads(j)
        assert parsed["status"] == "completed"

    def test_markdown_report(self):
        from overdrive.training_backend import MockTrainingBackend
        from overdrive.training_report import generate_training_markdown
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        md = generate_training_markdown(run)
        assert "Training Run Report" in md
        assert "Training Metrics" in md
        assert "Evaluation" in md
        assert "simulated" in md.lower()

    def test_model_card(self):
        from overdrive.training_backend import MockTrainingBackend
        from overdrive.training_report import generate_model_card
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        card = generate_model_card(run)
        assert "Model Card" in card
        assert "Qwen2.5-7B" in card
        assert "simulated" in card.lower()

    def test_no_governance_language(self):
        from overdrive.training_backend import MockTrainingBackend
        from overdrive.training_report import generate_training_markdown, generate_model_card
        run = MockTrainingBackend(seed=42).run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        for text in [generate_training_markdown(run), generate_model_card(run)]:
            lower = text.lower()
            for banned in ["governance", "compliance", "remediation", "admissibility", "authority"]:
                assert banned not in lower, f"Report contains '{banned}'"


# --- Stage 8: E2E ---

class TestE2ETrainingFlow:

    def test_full_incident_rca_finetune_flow(self):
        from overdrive.training_backend import MockTrainingBackend
        from overdrive.training_report import generate_training_markdown, generate_model_card
        backend = MockTrainingBackend(seed=42)
        run = backend.run("incident_rca_finetune", "qwen_2_5_7b", "synthetic_incident_rca_v1")
        assert run.status == "completed"
        assert run.evaluation["improvement"] > 0
        candidate = backend.create_serving_candidate(run)
        assert candidate.status == "simulated_ready"
        md = generate_training_markdown(run)
        assert len(md) > 200
        card = generate_model_card(run)
        assert len(card) > 100

    def test_all_tasks_can_run(self):
        from overdrive.training_backend import MockTrainingBackend
        from overdrive.training_models import TRAINING_TASKS
        backend = MockTrainingBackend(seed=42)
        for task_id, task in TRAINING_TASKS.items():
            model = task["model_profiles"][0]
            dataset = task["datasets"][0]
            run = backend.run(task_id, model, dataset)
            assert run.status == "completed", f"{task_id} did not complete"


class TestFrontendWiring:

    def test_page_exists(self, project_root):
        assert (project_root / "frontend" / "src" / "pages" / "TrainingDemo.tsx").exists()

    def test_route_exists(self, project_root):
        app = (project_root / "frontend" / "src" / "App.tsx").read_text()
        assert "/training" in app

    def test_nav_exists(self, project_root):
        layout = (project_root / "frontend" / "src" / "components" / "AppLayout.tsx").read_text()
        assert "/training" in layout

    def test_api_methods(self, project_root):
        client = (project_root / "frontend" / "src" / "api" / "client.ts").read_text()
        assert "/v1/training" in client
