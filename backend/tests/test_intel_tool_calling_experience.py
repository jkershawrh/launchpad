import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "content-intel-llm-tool-calling/modules/ROOT/pages"
ANTORA = ROOT / "content-intel-llm-tool-calling/antora.yml"
CATALOG = ROOT / "catalog/intel-llm-tool-calling/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/intel-llm-tool-calling.yaml"
CERTIFICATION = ROOT / "certification/catalog/intel-llm-tool-calling.yaml"
SEAT_CERTIFIER = ROOT / "scripts/certify-tool-calling-seat.sh"
JOURNEY_CERTIFIER = ROOT / "scripts/certify-tool-calling-journey.sh"
CONTENT_REVISION = "13e8119b807735b5b8ba161d2daf8e462e7baeb7"
WORKLOAD_REVISION = "fc6a574694b531a89c4417309c6f74c144130576"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_tool_calling_canonical_mapping_and_published_provenance_are_exact():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    metadata = catalog["metadata"]

    assert catalog["catalog_item_id"] == "intel-llm-tool-calling"
    assert catalog["status"] == "draft"
    assert metadata["content_only"] is True
    assert metadata["showroom_content_repo_url"] == "https://github.com/jkershawrh/launchpad.git"
    assert metadata["showroom_content_ref"] == CONTENT_REVISION
    assert intake["sources"]["showroom"]["revision"] == CONTENT_REVISION
    assert metadata["source_content_repo"] == "https://github.com/rh-ai-quickstart/vllm-tool-calling.git"
    assert metadata["source_content_revision"] == WORKLOAD_REVISION
    assert metadata["workload_revision"] == WORKLOAD_REVISION
    assert intake["sources"]["workload"]["revision"] == WORKLOAD_REVISION
    antora = _load(ANTORA)
    assert antora["asciidoc"]["attributes"]["quickstart_repo"] == metadata["source_content_repo"]
    assert intake["certification"]["certified_seats"] == 0
    assert intake["certification"]["max_workshop_seats"] == 1
    assert metadata["certification_stage"] == "immutable-source-published"
    assert intake["certification"]["stage"] == "immutable-source-published"
    blockers = " ".join(intake["certification"]["activation_blockers"])
    assert "strict-TLS managed inference" in blockers


def test_tool_calling_publication_candidate_is_one_seat_only():
    catalog = _load(CATALOG)
    intake = _load(INTAKE)
    contract = _load(CERTIFICATION)

    assert catalog["metadata"]["max_workshop_seats"] == 1
    assert catalog["metadata"]["promotion_sequence"] == [1]
    assert intake["certification"]["max_workshop_seats"] == 1
    assert intake["certification"]["promotion_sequence"] == [1]
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [1]


def test_tool_calling_review_records_the_exact_published_candidate_boundary():
    review = _load(ROOT / "evidence/lab-experience-review-20260930.yaml")
    lab = review["labs"]["intel-llm-tool-calling"]
    source_state = lab["source_state"]

    assert lab["overall_status"] == "immutable-source-published-draft"
    assert source_state["published_revision"] == CONTENT_REVISION
    assert source_state["candidate_revision"] == CONTENT_REVISION
    assert source_state["workload_revision"] == WORKLOAD_REVISION
    assert source_state["certification_transfer"] == "none"
    assert "fresh one-seat" in source_state["certification_boundary"].lower()
    assert "backend placement explicitly unverified" in lab["next_action"]


def test_tool_calling_story_and_operator_surfaces_are_truthful():
    intake = _load(INTAKE)
    index = (PAGES / "index.adoc").read_text()

    assert "== The Scenario" in index
    assert "== Show → Learn → Do → Prove" in index
    assert "There is no application UI" in index
    assert "does not deploy or call an MCP server" in index
    assert "Showroom guide is the *Story* view" in index
    assert "*Terminal* is the tool workspace" in index
    assert "*OpenShift Console* is the platform view" in index
    assert "you will prove that an" not in index
    assert "platform declaration" in index
    assert [tab["id"] for tab in intake["runtime"]["tabs"]] == [
        "terminal",
        "openshift-console",
    ]
    assert intake["runtime"]["tabs"][0]["source"] == "showroom.terminal"
    assert intake["runtime"]["tabs"][1]["source"] == "cluster.console_url"


def test_tool_calling_execute_blocks_use_strict_tls_and_fail_on_http_errors():
    corpus = "\n".join(path.read_text() for path in sorted(PAGES.glob("*.adoc")))
    curl_commands = re.findall(r"^curl\s+[^\n]+", corpus, re.MULTILINE)

    assert corpus.count('role="execute"') == 30
    assert curl_commands
    assert all(command.startswith("curl -fsS ") for command in curl_commands)
    assert "--insecure" not in corpus

    for path in (SEAT_CERTIFIER, JOURNEY_CERTIFIER):
        script = path.read_text()
        assert "curl -k" not in script
        assert "curl -fsSk" not in script
        assert "curl_options=(-fsSk" not in script
        assert "config-arena" not in script
        assert "ARENA_INGRESS_IP" not in script

    seat = SEAT_CERTIFIER.read_text()
    journey = JOURNEY_CERTIFIER.read_text()
    assert 'model_key="' not in seat
    assert 'api_key="' not in journey
    assert '${MAAS_API_KEY}' in seat
    assert '${MAAS_API_KEY}' in journey
    assert 'actual_cluster" == "$expected_cluster' in journey


def test_tool_calling_certification_proves_model_and_tool_participation_truth():
    contract = _load(CERTIFICATION)
    assertions = {
        (item["path"], item.get("equals"))
        for item in contract["spec"]["seat_probe"]["json_assertions"]
    }

    assert ("model.name", "granite-3.2-8b-tools") in assertions
    assert ("model.inference_participated", True) in assertions
    assert ("model.backend_placement_verified", False) in assertions
    assert ("tool.execution_mode", "deterministic-local-function") in assertions
    assert ("tool.mcp_participated", False) in assertions
    assert ("tool.result_returned_to_model", True) in assertions
    assert ("provenance.showroom_revision", CONTENT_REVISION) in assertions
    assert ("provenance.workload_revision", WORKLOAD_REVISION) in assertions

    certifier = SEAT_CERTIFIER.read_text()
    assert 'index($model) != null' in certifier
    assert "inference_participated:true" in certifier
    assert "backend_placement_verified:false" in certifier
    assert 'execution_mode:"deterministic-local-function"' in certifier
    assert "mcp_participated:false" in certifier
