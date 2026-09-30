from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _corpus(component: str) -> str:
    pages = ROOT / component / "modules" / "ROOT" / "pages"
    return "\n".join(path.read_text() for path in sorted(pages.glob("*.adoc")))


def test_cpu_serving_uses_measured_results_not_unqualified_performance_or_cost_claims():
    corpus = _corpus("content-intel-llm-cpu-serving")
    for unsupported in (
        "No additional hardware cost",
        "production-grade inference endpoint",
        "*First token* -- 1-3 seconds",
        "*Generation* -- 10-30 tokens per second",
        "*Total for 200 tokens* -- 5-15 seconds",
    ):
        assert unsupported not in corpus
    assert "Record the values you actually observe" in corpus
    assert "Show → Learn → Do → Prove" in corpus


def test_tool_calling_does_not_present_unmeasured_savings_as_fact():
    corpus = _corpus("content-intel-llm-tool-calling")
    for unsupported in (
        "No additional hardware cost",
        "Additional hardware cost: zero",
        "$0/incremental hardware cost",
        "$2,000+/month GPU instance",
        "at a fraction of the cost",
    ):
        assert unsupported not in corpus
    assert "cost comparison requires measured" in corpus
    assert "Show → Learn → Do → Prove" in corpus


def test_agent_201_matches_the_single_assigned_model_and_closes_cleanly():
    corpus = _corpus("content-intel-xeon6-agent-201")
    assert "Compared two models on quality and latency" not in corpus
    assert "swapping models" not in corpus
    assert "Show → Learn → Do → Prove" in corpus
    assert "== Cleanup and Reclaim Boundary" in corpus
    for resource in ("solution-agent", "solution-tools", "solution-ui", "advisor-prompt"):
        assert resource in corpus
    assert "Do not delete the project" in corpus
    assert "apps.arena" not in corpus
