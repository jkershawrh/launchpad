from pathlib import Path

import yaml
from app.adapters.file.catalog import FileCatalogAdapter
from app.domain.enums import CatalogStatus
from app.services.catalog_onboarding import build_catalog_item, load_intake

ROOT = Path(__file__).resolve().parents[2]
INTAKE_PATH = ROOT / "catalog-onboarding/multi-agent-quickstart.yaml"
CATALOG_PATH = ROOT / "catalog/multi-agent-quickstart/catalog-item.yaml"
CONTENT_ROOT = ROOT / "content-multi-agent-quickstart"
TRACKS = {
    "track-1-local": "track-1-local.adoc",
    "track-2-openshift": "track-2-openshift.adoc",
    "track-3-blueprint": "track-3-blueprint.adoc",
}


def test_multi_agent_quickstart_is_active_for_public_event_orders():
    intake = load_intake(INTAKE_PATH)
    catalog = yaml.safe_load(CATALOG_PATH.read_text())

    assert catalog == build_catalog_item(intake)
    assert catalog["catalog_item_id"] == "multi-agent-quickstart"
    assert catalog["display_name"] == "Build Multi-Agent AI Systems with Open Protocols"
    assert catalog["version"] == "0.2.14"
    assert catalog["status"] == "active"
    assert catalog["metadata"]["onboarding_managed"] is True
    assert catalog["metadata"]["activation_blockers"] == []
    assert catalog["metadata"]["allowed_exposure_policies"] == [
        "internal",
        "public_code",
    ]
    assert catalog["metadata"]["production_blockers"]
    assert catalog["metadata"]["certification_stage"] == "thirty-seat-certified"
    assert catalog["metadata"]["max_workshop_seats"] == 30
    assert catalog["metadata"]["certification_proof_contract"] == (
        "certification/catalog/multi-agent-quickstart.yaml"
    )


def test_multi_agent_quickstart_preserves_immutable_source_provenance():
    intake = load_intake(INTAKE_PATH)
    catalog = build_catalog_item(intake)
    metadata = catalog["metadata"]

    assert metadata["source_references"]["original_lab"] == {
        "repo_url": "https://github.com/jkershawrh/multi-agent-quickstart.git",
        "revision": "159113ab9f8df39e09e08926b51c7c32da0fc1af",
        "path": ".",
    }
    assert metadata["workload_repo"] == "https://github.com/rhpds/launchpad.git"
    assert metadata["workload_revision"] == (
        "100bcd4d4dd40e2ab74b59e984112c3d86fbac9b"
    )
    assert len(metadata["workload_revision"]) == 40
    assert metadata["workload_deploy_path"] == "deploy/workloads/multi-agent-seat"
    assert metadata["workload_source_kind"] == "launchpad-seat-chart"
    assert metadata["workload_gitops_ready"] is True
    assert metadata["workload_identity_value_path"] == "identity"
    assert metadata["workload_runtime_secret_name"] == "multi-agent-runtime"
    assert metadata["workload_runtime_secret_value_path"] == "runtime.existingSecret"
    assert metadata["workload_runtime_secret_sources"] == {
        "MODEL_ENDPOINT": {"source": "maas_api_url"},
        "MODEL_API_KEY": {"source": "maas_api_key"},
        "MODEL_NAME": {"source": "requested_model"},
        "AGENT_AUTH_TOKEN": {"source": "generated_password", "length": 48},
    }
    assert metadata["workload_helm_values"] == {
        "image": {
            "repository": "quay.io/rh-ee-jkershaw/launchpad-multi-agent-quickstart",
            "digest": (
                "sha256:84f6be95993f6481b4d99f9e0d68e98e12d0ea9c992d204164a3688503e1c661"
            ),
        }
    }


def test_multi_agent_showroom_is_native_launchpad_content():
    playbook = yaml.safe_load((ROOT / "site-multi-agent-quickstart.yml").read_text())
    component = yaml.safe_load((CONTENT_ROOT / "antora.yml").read_text())
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    guide = "\n".join(path.read_text() for path in sorted(pages.glob("*.adoc")))

    assert playbook["content"]["sources"] == [
        {"url": ".", "start_path": "content-multi-agent-quickstart"}
    ]
    assert "releases/download/patternfly-6/" in playbook["ui"]["bundle"]["url"]
    catalog = yaml.safe_load(CATALOG_PATH.read_text())
    assert catalog["metadata"]["showroom_content_ref"] == (
        "86c7f1a0e51164fa3c854b0a7a8236fd090014f9"
    )
    assert component["asciidoc"]["attributes"]["project_name"] == "%namespace%"
    assert component["asciidoc"]["attributes"]["maas_model"] == "%maas_model%"
    assert "Launchpad has already authenticated this terminal" in guide
    assert "oc login -u" not in guide
    for concept in (
        "A2A",
        "semantic routing",
        "MCP",
        "guardrails",
        "OpenTelemetry",
    ):
        assert concept in guide


def test_multi_agent_is_one_lab_with_all_three_upstream_tracks():
    catalog = yaml.safe_load(CATALOG_PATH.read_text())
    metadata = catalog["metadata"]
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    nav = (CONTENT_ROOT / "modules/ROOT/nav.adoc").read_text()
    index = (pages / "index.adoc").read_text()

    assert metadata["single_environment"] is True
    assert metadata["track_count"] == 3
    assert [track["id"] for track in metadata["learning_tracks"]] == list(TRACKS)
    assert [track["title"] for track in metadata["learning_tracks"]] == [
        "Understand the application pattern",
        "Build and operate on OpenShift",
        "Advanced blueprint alignment",
    ]

    for track_id, filename in TRACKS.items():
        assert (pages / filename).is_file()
        assert f"xref:{filename}" in nav
        assert f"xref:{filename}" in index
        assert track_id in (pages / filename).read_text()

    assert "one catalog item" in index
    assert "one participant environment" in index


def test_multi_agent_track_scope_is_explicit_and_does_not_overclaim_track_three():
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    track_1 = (pages / TRACKS["track-1-local"]).read_text()
    track_2 = (pages / TRACKS["track-2-openshift"]).read_text()
    track_3 = (pages / TRACKS["track-3-blueprint"]).read_text()

    assert "Docker Compose" in track_1
    assert "pre-provisioned OpenShift runtime" in track_1
    assert "Track 2: Build and Operate on OpenShift" in track_2
    assert "oc auth can-i" in track_2
    assert "oc create configmap workflow-policy" in track_2
    assert "AGENT_MAX_TOKENS_OVERRIDE=48" in track_2
    assert "oc rollout restart deployment/multi-agent" in track_2
    for agent in ("research", "analyst", "executor"):
        assert agent in track_2
    assert "Learner Evidence" in track_2
    assert "Kagenti" in track_3
    assert "OpenTelemetry" in track_3
    assert "not an end-to-end validated deployment" in track_3


def test_multi_agent_showroom_has_one_linear_pilot_journey():
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    nav = (CONTENT_ROOT / "modules/ROOT/nav.adoc").read_text()
    index = (pages / "index.adoc").read_text()
    track_1 = (pages / TRACKS["track-1-local"]).read_text()

    expected_order = [
        "index.adoc",
        "track-1-local.adoc",
        "01-architecture.adoc",
        "02-explore.adoc",
        "03-run-workflows.adoc",
        "04-tools-and-guardrails.adoc",
        "track-2-openshift.adoc",
        "05-customize.adoc",
        "track-3-blueprint.adoc",
        "99-conclusion.adoc",
    ]
    assert [
        line.split("xref:", 1)[1].split("[", 1)[0]
        for line in nav.splitlines()
        if "xref:" in line
    ] == expected_order
    assert "Choose Your Track" not in nav
    assert "Shared Hands-On Exercises" not in nav
    assert "follow this sequence from top to bottom" in " ".join(index.split())
    assert "any or all three" not in index
    assert "Track 1: Understand the Application Pattern" in track_1
    assert track_1.index("== Run Your First Workflow") < track_1.index(
        "== Inspect the Application Topology"
    )

    next_page = {
        "index.adoc": "track-1-local.adoc",
        "track-1-local.adoc": "01-architecture.adoc",
        "01-architecture.adoc": "02-explore.adoc",
        "02-explore.adoc": "03-run-workflows.adoc",
        "03-run-workflows.adoc": "04-tools-and-guardrails.adoc",
        "04-tools-and-guardrails.adoc": "track-2-openshift.adoc",
        "track-2-openshift.adoc": "05-customize.adoc",
        "05-customize.adoc": "track-3-blueprint.adoc",
        "track-3-blueprint.adoc": "99-conclusion.adoc",
    }
    for source, destination in next_page.items():
        assert f"xref:{destination}[" in (pages / source).read_text()

    for module in expected_order[1:-1]:
        assert "Checkpoint" in (pages / module).read_text(), module


def test_track_one_teaches_the_participant_ui_workflow_and_checkpoint_concepts():
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    track_1 = (pages / TRACKS["track-1-local"]).read_text()
    workflows = (pages / "03-run-workflows.adoc").read_text()
    track_1_text = " ".join(track_1.split())
    workflows_text = " ".join(workflows.split())

    assert "entering each request in the *Fictional incident or operations request* box" in track_1_text
    assert "clicking *Investigate Incident*" in track_1_text
    for panel in (
        "Incident Response Package",
        "Supporting Evidence",
        "Why This Response Path Was Selected",
    ):
        assert f"=== {panel}" in track_1
    for explanation in (
        "SIMPLE`, `MEDIUM`, `COMPLEX`, or `REASONING",
        "A2A agent card",
        "not hidden model reasoning",
        "Input guardrails run before",
        "Output guardrails run after",
    ):
        assert explanation in track_1_text

    assert "open *Technical Details*, expand *Runtime health*, and click *Refresh*" in workflows_text
    assert "Agents discovered: 3" in workflows_text
    assert "research`, `analyst`, and `executor" in workflows_text
    assert "health panel" not in workflows_text


def test_multi_agent_journey_leads_with_a_business_workload_and_takeaway():
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    index = (pages / "index.adoc").read_text()
    track_1 = (pages / TRACKS["track-1-local"]).read_text()
    conclusion = (pages / "99-conclusion.adoc").read_text()
    guide = "\n".join((index, track_1, conclusion))

    for phrase in (
        "fictional service incident",
        "business workload",
        "openshift workload",
        "incident response package",
        "human review",
    ):
        assert phrase in guide.lower()

    assert "The system is domain-agnostic" not in index
    assert "Gather Evidence" in track_1
    assert "Assess Likely Causes" in track_1
    assert "Prepare a Governed Action" in track_1
    assert "reusable incident-response blueprint" in conclusion.lower()


def test_mcp_walkthrough_uses_the_server_contract_tool_name():
    page = (
        CONTENT_ROOT / "modules/ROOT/pages/04-tools-and-guardrails.adoc"
    ).read_text()

    assert '"name":"search_knowledge_base"' in page
    assert '"name":"knowledge_search"' not in page


def test_track_two_explains_expected_rbac_warning_and_workload_pod():
    page = (
        CONTENT_ROOT / "modules/ROOT/pages" / TRACKS["track-2-openshift"]
    ).read_text()
    page_text = " ".join(page.split())

    assert "is silent when the project is correct" in page_text
    assert "resource 'nodes' is not namespace scoped" in page_text
    assert "informational" in page_text
    assert "the final result must be `no`" in page_text
    assert "A `Forbidden` response is also an expected denial" in page_text
    assert "Deployment named `multi-agent` creates one seat-specific workload pod" in page_text
    assert "app.kubernetes.io/name=multi-agent-seat" in page
    for container in (
        "orchestrator",
        "research",
        "analyst",
        "executor",
        "mcp-server",
        "guardrails",
        "participant-ui",
    ):
        assert f"`{container}`" in page


def test_multi_agent_quickstart_is_orderable_after_internal_promotion():
    adapter = FileCatalogAdapter(str(ROOT / "catalog"))

    assert adapter.validate_item("multi-agent-quickstart") is True
    assert adapter.set_status(
        "multi-agent-quickstart", CatalogStatus.ACTIVE
    ).status == CatalogStatus.ACTIVE


def test_track_two_certification_executes_and_cleans_the_learner_change():
    probe = (ROOT / "scripts/certify-multi-agent-seat.sh").read_text()

    for command in (
        'stage="learner-policy-apply"',
        "oc create configmap workflow-policy",
        "oc rollout restart deployment/multi-agent",
        "import agent; print(agent.AGENT_MAX_TOKENS)",
        "oc delete configmap workflow-policy",
    ):
        assert command in probe
    assert "rollback_restored_baseline" in probe
    assert "configmap_removed" in probe


def test_showroom_commands_do_not_collide_with_content_or_wetty_ports():
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    explore = (pages / "02-explore.adoc").read_text()
    workflows = (pages / "03-run-workflows.adoc").read_text()
    tools_and_guardrails = (pages / "04-tools-and-guardrails.adoc").read_text()

    assert "service/multi-agent 18000:8000" in explore
    assert "service/multi-agent-research 18001:8001" in explore
    assert "127.0.0.1:18000/health" in explore
    assert "127.0.0.1:18001/.well-known/agent-card.json" in explore
    assert "127.0.0.1:18000/api/v1/workflow" in workflows
    assert "jsonpath='{.data.AGENT_AUTH_TOKEN}' | base64 -d" in workflows
    assert 'test -n "$AGENT_AUTH_TOKEN"' in workflows
    assert "service/multi-agent-orchestrator" not in explore
    assert "service/multi-agent-mcp 18004:8004" in tools_and_guardrails
    assert "127.0.0.1:18004/health" in tools_and_guardrails
    assert "service/multi-agent-mcp-server" not in tools_and_guardrails


def test_workspace_and_guardrail_steps_name_the_exact_ui_controls():
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    workflows = (pages / "03-run-workflows.adoc").read_text()
    guardrails = (pages / "04-tools-and-guardrails.adoc").read_text()
    track_two = (pages / "track-2-openshift.adoc").read_text()

    for page in (workflows, track_two):
        page_text = " ".join(page.lower().split())
        assert "expand *advanced response options*" in page_text
        assert "*Response depth*" in page
        assert "`comprehensive`" in page
        assert "*Investigate Incident*" in page

    assert "*Fictional incident or operations request*" in guardrails
    assert "*Investigate Incident*" in guardrails
    assert "Request blocked by guardrails" in guardrails
