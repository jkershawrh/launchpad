from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = ROOT / "content-scale-agentic-blueprint"
PAGES = CONTENT_ROOT / "modules/ROOT/pages"


def test_scale_content_follows_the_workload_journey_without_launchpad_seat_steps():
    nav = (CONTENT_ROOT / "modules/ROOT/nav.adoc").read_text()
    expected = [
        "index.adoc",
        "01-success-envelope.adoc",
        "02-platform-proof.adoc",
        "02-trace-baseline.adoc",
        "03-evaluate-baseline.adoc",
        "04-scale-workload.adoc",
        "05-quality-policy.adoc",
        "06-failure-recovery.adoc",
        "07-operating-envelope.adoc",
        "99-conclusion.adoc",
    ]
    assert [
        line.split("xref:", 1)[1].split("[", 1)[0]
        for line in nav.splitlines()
        if "xref:" in line
    ] == expected

    guide = "\n".join((PAGES / name).read_text() for name in expected)
    assert "one assigned OpenShift namespace" in guide
    assert "Baseline | 1 | 1" in guide
    assert "Sustained | 2 | 5" in guide
    assert "Pressure | 3 | 10" in guide
    assert "25 participants" in guide
    assert "not a learner exercise" in guide
    assert "OpenShift Sandbox terminal" in guide
    assert "OpenShift Console" in guide
    assert "OpenTelemetry trace" in guide
    assert "same journey ID" in guide


def test_scale_content_preserves_truth_and_authority_boundaries():
    guide = "\n".join(path.read_text() for path in sorted(PAGES.glob("*.adoc")))
    normalized = guide.lower()

    for phrase in (
        "not an orderable lab",
        "never present planned thresholds",
        "human review",
        "zero unsupported claims",
        "Shared endpoint CPU utilization is never labeled",
        "does not certify",
    ):
        assert phrase.lower() in normalized


def test_scale_showroom_playbook_uses_local_draft_content():
    playbook = yaml.safe_load((ROOT / "site-scale-agentic-blueprint.yml").read_text())
    component = yaml.safe_load((CONTENT_ROOT / "antora.yml").read_text())

    assert playbook["content"]["sources"] == [
        {"url": ".", "start_path": "content-scale-agentic-blueprint"}
    ]
    assert component["asciidoc"]["attributes"]["project_name"] == "%namespace%"
