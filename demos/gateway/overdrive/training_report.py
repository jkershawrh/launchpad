"""Training run reports — JSON, Markdown, and model cards."""

import json
from datetime import datetime, timezone
from dataclasses import asdict


def generate_training_json(training_run) -> str:
    return json.dumps(asdict(training_run), indent=2, default=str)


def generate_training_markdown(training_run) -> str:
    m = training_run.metrics
    e = training_run.evaluation
    a = training_run.artifacts

    lines = [
        "# Inference Overdrive: Training Run Report",
        "",
        "## Run Summary",
        f"- **Training run:** {training_run.training_run_id}",
        f"- **Demo task:** {training_run.demo_task}",
        f"- **Model profile:** {training_run.model_profile_id} ({training_run.base_model_name})",
        f"- **Dataset:** {training_run.dataset_id} ({training_run.dataset_version})",
        f"- **Training mode:** {training_run.training_mode}",
        f"- **Hardware lane:** {training_run.hardware_lane}",
        f"- **Status:** {training_run.status}",
        f"- **Simulated:** {'Yes' if m.get('simulated') else 'No'}",
        "",
        "## Training Metrics",
        f"- **Samples seen:** {m.get('samples_seen', 0):,}",
        f"- **Duration:** {m.get('training_duration_seconds', 0):.0f} seconds",
        f"- **Start loss:** {m.get('train_loss_start', 0):.3f}",
        f"- **End loss:** {m.get('train_loss_end', 0):.3f}",
        "",
        "## Evaluation",
        f"- **Base score:** {e.get('base_score', 0):.3f}",
        f"- **Tuned score:** {e.get('tuned_score', 0):.3f}",
        f"- **Improvement:** +{e.get('improvement', 0):.3f}",
        "",
    ]

    dims = e.get("dimensions", {})
    if dims:
        lines.append("### Score Breakdown")
        lines.append("")
        lines.append("| Dimension | Base | Tuned | Delta |")
        lines.append("|-----------|------|-------|-------|")
        for dim_name, scores in dims.items():
            base = scores.get("base", 0)
            tuned = scores.get("tuned", 0)
            delta = tuned - base
            lines.append(f"| {dim_name} | {base:.3f} | {tuned:.3f} | +{delta:.3f} |")
        lines.append("")

    lines.extend([
        "## Artifacts",
        f"- **Adapter ref:** {a.get('adapter_ref', 'N/A')}",
        f"- **Model card:** {a.get('model_card_ref', 'N/A')}",
        "",
        "## Notes",
        "- Training metrics are **simulated** unless real backend mode is enabled.",
        "- Evaluation scores are deterministic from seed for reproducibility.",
        f"- Report generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ])
    return "\n".join(lines)


def generate_model_card(training_run) -> str:
    e = training_run.evaluation
    m = training_run.metrics

    lines = [
        f"# Model Card: {training_run.base_model_name} — {training_run.demo_task}",
        "",
        "## Model Details",
        f"- **Base model:** {training_run.base_model_name}",
        f"- **Profile:** {training_run.model_profile_id}",
        f"- **Fine-tuning task:** {training_run.demo_task}",
        f"- **Training mode:** {training_run.training_mode}",
        f"- **Hardware:** {training_run.hardware_lane}",
        f"- **Dataset:** {training_run.dataset_id}",
        "",
        "## Training Summary",
        f"- **Samples:** {m.get('samples_seen', 0):,}",
        f"- **Loss:** {m.get('train_loss_start', 0):.3f} → {m.get('train_loss_end', 0):.3f}",
        f"- **Duration:** {m.get('training_duration_seconds', 0):.0f}s",
        "",
        "## Performance",
        f"- **Before fine-tuning:** {e.get('base_score', 0):.3f}",
        f"- **After fine-tuning:** {e.get('tuned_score', 0):.3f}",
        f"- **Improvement:** +{e.get('improvement', 0):.3f}",
        "",
        "## Intended Use",
        f"This fine-tuned model is designed for **{training_run.demo_task}** tasks",
        f"and should be served on the **{training_run.hardware_lane}** lane.",
        "",
        "## Limitations",
        "- This is a simulated training run for demo purposes.",
        "- Actual model quality depends on real training with production data.",
        "",
    ]
    return "\n".join(lines)
