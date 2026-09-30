from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / "content-operate-agentic-blueprint" / "modules" / "ROOT" / "pages"


def _page(name: str) -> str:
    return (CONTENT / name).read_text()


def test_401_has_story_show_learn_do_prove_and_progression():
    overview = _page("index.adoc")
    for marker in (
        "== Story",
        "Show → Learn → Do → Prove",
        "level 301",
        "level 501",
        "OpenShift Console",
        "Multi-Agent Workspace",
        "Intel Xeon",
    ):
        assert marker in overview


def test_401_restores_observed_baseline_instead_of_a_magic_value():
    policy = _page("03-policy.adoc")
    change = _page("05-change-proof.adoc")
    assert "agentic-401-baseline-max-tokens" in policy
    assert "agentic-401-baseline-max-tokens" in change
    assert 'print(agent.AGENT_MAX_TOKENS)\')\") = "96"' not in change


def test_401_closes_with_participant_cleanup_and_platform_reclaim_boundary():
    conclusion = _page("99-conclusion.adoc")
    assert "== Clean Up the Learner Session" in conclusion
    assert "rm -f /tmp/agentic-401" in conclusion
    assert "Launchpad reclaim" in conclusion
    assert "zero-residue" in conclusion
