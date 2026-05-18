"""Mock training backend — deterministic simulated training runs."""

import math
import random
import uuid
from datetime import datetime, timezone

from .training_models import (
    TrainingRun, ServingCandidate, MODEL_PROFILES, DATASET_PROFILES,
    TRAINING_TASKS, VALID_TRAINING_MODES,
)


class MockTrainingBackend:
    def __init__(self, seed: int = 42):
        self._seed = seed

    def run(self, demo_task: str, model_profile_id: str, dataset_id: str,
            training_mode: str = "mock_lora", seed: int = None) -> TrainingRun:
        s = seed if seed is not None else self._seed
        rng = random.Random(s)

        if model_profile_id not in MODEL_PROFILES:
            raise ValueError(f"Unknown model profile: {model_profile_id}")
        if dataset_id not in DATASET_PROFILES:
            raise ValueError(f"Unknown dataset: {dataset_id}")
        if training_mode not in VALID_TRAINING_MODES:
            raise ValueError(f"Unknown training mode: {training_mode}")

        model = MODEL_PROFILES[model_profile_id]
        dataset = DATASET_PROFILES[dataset_id]

        run_id = f"train-{demo_task[:20]}-{uuid.UUID(int=rng.getrandbits(128)).hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        loss_start = round(rng.uniform(1.8, 2.5), 3)
        loss_end = round(rng.uniform(0.6, 1.1), 3)
        loss_curve = _generate_loss_curve(loss_start, loss_end, steps=20, seed=s)

        base_score = round(rng.uniform(0.55, 0.70), 3)
        improvement = round(rng.uniform(0.15, 0.30), 3)
        tuned_score = round(min(base_score + improvement, 0.95), 3)

        duration = round(rng.uniform(300, 900), 1)
        samples = dataset.get("train_count", 800)

        training_run = TrainingRun(
            training_run_id=run_id,
            demo_task=demo_task,
            model_profile_id=model_profile_id,
            base_model_name=model["name"],
            dataset_id=dataset_id,
            dataset_version=dataset.get("version", "v1"),
            training_mode=training_mode,
            hardware_lane=model.get("training_lane", "gaudi_overdrive"),
            status="completed",
            started_at=now,
            completed_at=now,
            loss_curve=loss_curve,
            metrics={
                "train_loss_start": loss_start,
                "train_loss_end": loss_end,
                "training_duration_seconds": duration,
                "samples_seen": samples,
                "simulated": True,
            },
            artifacts={
                "adapter_ref": f"artifacts/{run_id}/lora-adapter",
                "model_card_ref": f"artifacts/{run_id}/model-card.md",
            },
            evaluation={
                "base_score": base_score,
                "tuned_score": tuned_score,
                "improvement": round(tuned_score - base_score, 3),
                "dimensions": {
                    "format": {"base": round(base_score + rng.uniform(-0.05, 0.05), 3), "tuned": round(tuned_score + rng.uniform(-0.05, 0.05), 3)},
                    "relevance": {"base": round(base_score + rng.uniform(-0.08, 0.08), 3), "tuned": round(tuned_score + rng.uniform(-0.03, 0.05), 3)},
                    "technical_specificity": {"base": round(base_score - rng.uniform(0.05, 0.15), 3), "tuned": round(tuned_score + rng.uniform(0, 0.08), 3)},
                    "completeness": {"base": round(base_score + rng.uniform(-0.05, 0.1), 3), "tuned": round(tuned_score + rng.uniform(-0.05, 0.05), 3)},
                    "brevity": {"base": round(base_score + rng.uniform(0, 0.1), 3), "tuned": round(tuned_score + rng.uniform(-0.08, 0.05), 3)},
                },
            },
            metadata={"seed": s, "simulated": True, "source": "MockTrainingBackend"},
        )

        return training_run

    def create_serving_candidate(self, training_run: TrainingRun) -> ServingCandidate:
        model = MODEL_PROFILES.get(training_run.model_profile_id, {})
        return ServingCandidate(
            serving_candidate_id=f"serve-{training_run.training_run_id}",
            training_run_id=training_run.training_run_id,
            model_profile_id=training_run.model_profile_id,
            artifact_ref=training_run.artifacts.get("adapter_ref", ""),
            target_lane=model.get("serving_lane", "gaudi_overdrive"),
            status="simulated_ready",
            created_at=datetime.now(timezone.utc).isoformat(),
        )


def _generate_loss_curve(start: float, end: float, steps: int = 20, seed: int = 42) -> list[float]:
    rng = random.Random(seed)
    curve = []
    for i in range(steps):
        t = i / (steps - 1)
        smooth = start + (end - start) * (1 - math.exp(-3 * t))
        jitter = rng.uniform(-0.05, 0.05) * (1 - t)
        curve.append(round(max(end * 0.8, smooth + jitter), 4))
    return curve
