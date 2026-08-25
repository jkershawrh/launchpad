"""Contract for the repository-owned Antora/Nookbag Showroom package."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_antora_playbook_builds_content_from_this_repository():
    playbook = yaml.safe_load((ROOT / "site.yml").read_text())
    source = playbook["content"]["sources"][0]
    assert source["url"] == "."
    assert source["start_path"] == "content"
    assert "rhdp_showroom_theme" in playbook["ui"]["bundle"]["url"]


def test_operator_workshop_playbook_starts_on_operator_journey():
    playbook = yaml.safe_load((ROOT / "site-openshift-operators.yml").read_text())

    assert playbook["site"]["start_page"] == "modules::index.adoc"
    assert playbook["content"]["sources"][0]["start_path"] == "content-operators"
    assert playbook["asciidoc"]["attributes"]["showroom_journey"] == (
        "openshift-operators"
    )
    assert playbook["output"]["dir"] == "./www"

    operator_index = ROOT / "content-operators/modules/ROOT/pages/index.adoc"
    assert "OpenShift AI Operator Workshop" in operator_index.read_text()
    assert "Inference Overdrive" not in operator_index.read_text()


def test_nookbag_config_has_guided_workspace_tabs():
    config = yaml.safe_load((ROOT / "ui-config.yml").read_text())
    assert config["type"] == "showroom"
    assert config["view_switcher"]["default_mode"] == "split"
    names = [tab["name"] for tab in config["tabs"]]
    assert names == ["RAG Workspace", "Terminal", "OpenShift Console"]


def test_guided_rag_journey_is_versioned_as_asciidoc():
    page = ROOT / "content/modules/ROOT/pages/01-guided-rag-welcome.adoc"
    assert page.exists()
    assert "Guided RAG" in page.read_text()
    nav = (ROOT / "content/modules/ROOT/nav.adoc").read_text()
    assert "showroom_journey" in nav
    assert "01-guided-rag-welcome.adoc" in nav
