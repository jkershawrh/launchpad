"""Power report generation — JSON and Markdown output."""

import json
from datetime import datetime, timezone


def generate_json_report(metrics: dict) -> str:
    report = {**metrics, "generated_at": datetime.now(timezone.utc).isoformat()}
    return json.dumps(report, indent=2, default=str)


def generate_markdown_report(metrics: dict) -> str:
    rc = metrics.get("route_counts", {})
    lines = [
        "# Inference Overdrive Run Report",
        "",
        "## Run Summary",
        f"- **Mode:** {metrics.get('power_mode', 'N/A')}",
        f"- **Workload profile:** {metrics.get('workload_profile', 'N/A')}",
        f"- **Total requests:** {metrics.get('total_requests', 0):,}",
        f"- **Completed requests:** {metrics.get('completed_requests', 0):,}",
        f"- **Total estimated input tokens:** {metrics.get('total_input_tokens_estimate', 0):,}",
        f"- **Total estimated output tokens:** {metrics.get('total_output_tokens_estimate', 0):,}",
        "",
        "## Route Distribution",
        f"- **Xeon 6 Eco:** {rc.get('eco', 0):,} requests",
        f"- **Xeon 6 Performance:** {rc.get('performance', 0):,} requests",
        f"- **Gaudi Overdrive:** {rc.get('overdrive', 0):,} requests",
        "",
        "## Throughput",
        f"- **Requests/sec:** {metrics.get('requests_per_second', 0):.1f}",
        f"- **Estimated tokens/sec:** {metrics.get('estimated_tokens_per_second', 0):,.0f}",
        "",
        "## Latency",
        f"- **p50:** {metrics.get('p50_latency_ms', 0):.0f} ms",
        f"- **p95:** {metrics.get('p95_latency_ms', 0):.0f} ms",
        f"- **p99:** {metrics.get('p99_latency_ms', 0):.0f} ms",
        f"- **Min:** {metrics.get('min_latency_ms', 0):.0f} ms",
        f"- **Max:** {metrics.get('max_latency_ms', 0):.0f} ms",
        "",
        "## Power Summary",
        f"- **Xeon 6 handled:** {rc.get('eco', 0) + rc.get('performance', 0):,} requests ({metrics.get('xeon_eco_utilization_pct', 0) + metrics.get('xeon_performance_utilization_pct', 0):.0f}%)",
        f"- **Gaudi handled:** {rc.get('overdrive', 0):,} requests ({metrics.get('gaudi_overdrive_utilization_pct', 0):.0f}%)",
        f"- **Peak simulated overdrive utilization:** {metrics.get('gaudi_overdrive_utilization_pct', 0):.0f}%",
        "",
        "",
    ]

    mc = metrics.get("modality_counts", {})
    if mc and any(k != "text" for k in mc):
        lines.extend([
            "## Multimodal Summary",
            f"- **Total images:** {metrics.get('total_images', 0):,}",
            f"- **Total documents:** {metrics.get('total_documents', 0):,}",
            f"- **Total pages:** {metrics.get('total_pages', 0):,}",
            f"- **Images/sec:** {metrics.get('images_per_second', 0):.1f}",
            f"- **Documents/sec:** {metrics.get('documents_per_second', 0):.1f}",
            "",
            "## Modality Distribution",
        ])
        for modality, count in sorted(mc.items()):
            lines.append(f"- **{modality.capitalize()}:** {count:,} requests")
        lines.append("")

    lines.extend([
        "## Notes",
        "- Metrics are **simulated** unless real endpoint mode is enabled.",
        "- Token counts are estimates based on workload profile configuration.",
        f"- Report generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ])
    return "\n".join(lines)
