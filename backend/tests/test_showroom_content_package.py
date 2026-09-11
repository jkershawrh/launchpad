"""Contract for the repository-owned Antora/Nookbag Showroom package."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


INTEL_GUIDED_LABS = [
    {
        "catalog_id": "intel-xeon6-agent-201",
        "display_name": "Intel Xeon 6 201: Building an AI Agent",
        "playbook": "site-intel-xeon6-agent-201.yml",
        "content_path": "content-intel-xeon6-agent-201",
        "title": "Intel Xeon 6 201 — Building an AI Agent",
        "model": "granite-3.2-8b-tools",
        "workspace_route": "app",
        "content_ref": "pilot-2026-09-17-showroom-execute-v1.0.1",
        "max_workshop_seats": 25,
        "certification_stage": "twenty-five-seat",
    },
    {
        "catalog_id": "intel-llm-cpu-serving",
        "display_name": "Intel AI Quickstart: Serve LLMs on Intel Xeon CPUs",
        "playbook": "site-intel-llm-cpu-serving.yml",
        "content_path": "content-intel-llm-cpu-serving",
        "title": "Serve LLMs on Intel Xeon CPUs",
        "model": "granite-2b-cpu",
        "workspace_route": "rag",
        "content_ref": "pilot-2026-09-17-showroom-execute-v1.0.1",
        "max_workshop_seats": 25,
        "certification_stage": "twenty-five-seat",
    },
    {
        "catalog_id": "intel-llm-tool-calling",
        "display_name": "Intel AI Quickstart: LLM Tool Calling on Intel",
        "playbook": "site-intel-llm-tool-calling.yml",
        "content_path": "content-intel-llm-tool-calling",
        "title": "Enable AI Tool Calling on OpenShift",
        "model": "granite-3.2-8b-tools",
        "workspace_route": "",
        "content_ref": "pilot-2026-09-17-showroom-execute-v1.0.1",
        "max_workshop_seats": 25,
        "certification_stage": "twenty-five-seat",
    },
]


def test_antora_playbook_builds_content_from_this_repository():
    playbook = yaml.safe_load((ROOT / "site.yml").read_text())
    source = playbook["content"]["sources"][0]
    assert source["url"] == "."
    assert source["start_path"] == "content"
    assert "rhdp_showroom_theme" in playbook["ui"]["bundle"]["url"]


def test_shared_showroom_ui_adds_execute_without_removing_copy():
    supplemental = ROOT / "content/supplemental-ui"
    head = (supplemental / "partials/head-meta.hbs").read_text()
    script = (supplemental / "js/execute.js").read_text()
    styles = (supplemental / "css/site-extra.css").read_text()

    assert '{{uiRootPath}}/js/execute.js' in head
    assert '{{uiRootPath}}/css/site-extra.css' in head
    assert "div.listingblock.execute" in script
    assert "launchpad-execute-button" in script
    assert "Execute" in script
    assert "copy-button" not in script
    assert "findTerminalIframe" in script
    assert "xterm-helper-textarea" in script
    assert "Terminal unavailable" in script
    assert ".launchpad-execute-button" in styles


def test_operator_workshop_playbook_starts_on_operator_journey():
    playbook = yaml.safe_load((ROOT / "site-openshift-operators.yml").read_text())

    assert playbook["site"]["start_page"] == "modules::index.adoc"
    assert playbook["content"]["sources"][0]["start_path"] == "content-operators"
    assert playbook["asciidoc"]["attributes"]["showroom_journey"] == ("openshift-operators")
    assert playbook["output"]["dir"] == "./www"

    operator_index = ROOT / "content-operators/modules/ROOT/pages/index.adoc"
    assert "OpenShift AI Operator Workshop" in operator_index.read_text()
    assert "Inference Overdrive" not in operator_index.read_text()
    assert "*OpenShift Console* operator tab" in operator_index.read_text()
    assert "*launchpad-public*" in operator_index.read_text()
    assert "no separate OpenShift username" in operator_index.read_text()
    assert "{cluster_display_name}" in operator_index.read_text()
    assert "Oberon" not in operator_index.read_text()

    discovery = ROOT / "content-operators/modules/ROOT/pages/02-operator-discovery.adoc"
    assert "{cluster_display_name}" in discovery.read_text()
    assert "Oberon" not in discovery.read_text()

    exercise = ROOT / "content-operators/modules/ROOT/pages/03-deploy-and-observe.adoc"
    exercise_text = exercise.read_text()
    assert "quay.io/openshifttest/hello-openshift:1.2.0" in exercise_text
    assert "curl" in exercise_text


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


@pytest.mark.parametrize("lab", INTEL_GUIDED_LABS)
def test_intel_guided_lab_is_native_launchpad_content(lab):
    catalog = yaml.safe_load(
        (ROOT / "catalog" / lab["catalog_id"] / "catalog-item.yaml").read_text()
    )
    assert catalog["catalog_item_id"] == lab["catalog_id"]
    assert catalog["display_name"] == lab["display_name"]
    assert catalog["category"] == "guided_build"
    assert catalog["status"] == "active"
    assert set(catalog["required_capabilities"]) >= {
        "openshift",
        "showroom",
        "model_endpoint",
    }
    assert catalog["provisioner_refs"] == ["openshift-provisioner", "showroom"]
    assert catalog["validation_refs"] == [
        "pod-ready",
        "route-accessible",
        "inference-health",
    ]

    metadata = catalog["metadata"]
    assert metadata["showroom"] is True
    assert metadata["operator_workshop"] is True
    assert metadata["content_only"] is True
    assert metadata["max_workshop_seats"] == lab["max_workshop_seats"]
    assert metadata["certification_stage"] == lab["certification_stage"]
    assert metadata["required_models"] == [lab["model"]]
    assert metadata["showroom_content_repo_url"] == ("https://github.com/rhpds/launchpad.git")
    assert metadata["showroom_content_ref"] == lab["content_ref"]
    assert metadata["showroom_content_playbook"] == lab["playbook"]
    assert metadata.get("workspace_route_name", "") == lab["workspace_route"]

    # OpenShift's generated route host uses <route>-<namespace> as one DNS
    # label. Keep it below the 63-character label limit for the longest
    # namespace shape emitted by the Launchpad provisioner.
    if lab["workspace_route"]:
        tenant = "smoke-test-tenant"[:18]
        catalog_id = lab["catalog_id"][:18]
        namespace = f"launchpad-{tenant}-{catalog_id}-abcdef"
        assert len(f"{lab['workspace_route']}-{namespace}") <= 63

    playbook = yaml.safe_load((ROOT / lab["playbook"]).read_text())
    assert playbook["site"]["start_page"] == "modules::index.adoc"
    assert playbook["content"]["sources"] == [{"url": ".", "start_path": lab["content_path"]}]
    assert "rhdp_showroom_theme" in playbook["ui"]["bundle"]["url"]
    assert playbook["ui"]["supplemental_files"] == "./content/supplemental-ui"
    assert playbook["output"]["dir"] == "./www"

    component = yaml.safe_load((ROOT / lab["content_path"] / "antora.yml").read_text())
    assert component["title"] == lab["title"]
    assert component["asciidoc"]["attributes"]["project_name"] == "%namespace%"
    assert component["asciidoc"]["attributes"]["cluster_display_name"] == ("%cluster_display_name%")
    if lab["catalog_id"] == "intel-llm-tool-calling":
        assert component["asciidoc"]["attributes"]["maas_api_url"] == ("%maas_api_url%")

    nav = ROOT / lab["content_path"] / "modules/ROOT/nav.adoc"
    index = ROOT / lab["content_path"] / "modules/ROOT/pages/index.adoc"
    assert nav.exists()
    assert index.exists()
    assert "xref:" in nav.read_text()


@pytest.mark.parametrize("lab", INTEL_GUIDED_LABS)
def test_intel_guided_lab_uses_launchpad_sso_instructions(lab):
    pages = ROOT / lab["content_path"] / "modules/ROOT/pages"
    content = "\n".join(path.read_text() for path in sorted(pages.glob("*.adoc")))

    assert "oc login -u {user} -p {password}" not in content
    assert "*Password:* `{password}`" not in content
    assert "Launchpad has already authenticated this terminal" in content


def test_agent_content_uses_launchpad_safe_workload_manifests():
    content_root = ROOT / "content-intel-xeon6-agent-201"
    pages = content_root / "modules/ROOT/pages"
    content = "\n".join(path.read_text() for path in sorted(pages.glob("*.adoc")))

    assert "intel-guided-content-v1.0.13" in content
    assert "{litellm_api_endpoint}" not in content
    assert "{litellm_virtual_key}" not in content
    assert "{maas_endpoint}" in content
    assert "{maas_api_key}" not in content
    assert "$MAAS_API_KEY" in content
    component = yaml.safe_load((content_root / "antora.yml").read_text())
    attributes = component["asciidoc"]["attributes"]
    assert attributes["maas_endpoint"] == "%maas_endpoint%"
    assert "maas_api_key" not in attributes
    assert "raw.githubusercontent.com/rhpds/triforce" not in content
    assert "phi3-mini-cpu" not in content
    assert "qwen25-3b-cpu" not in content

    expected_routes = {
        "solution-tools.yaml": "tools",
        "solution-agent.yaml": "agent",
        "solution-ui.yaml": "app",
    }
    for filename, route_name in expected_routes.items():
        manifest = content_root / "manifests" / filename
        assert manifest.exists()
        resources = list(yaml.safe_load_all(manifest.read_text()))
        route = next(resource for resource in resources if resource["kind"] == "Route")
        assert route["metadata"]["name"] == route_name

    for filename in ("solution-agent.yaml", "solution-ui.yaml"):
        resources = list(yaml.safe_load_all((content_root / "manifests" / filename).read_text()))
        deployment = next(resource for resource in resources if resource["kind"] == "Deployment")
        assert all(
            "@sha256:" in container["image"]
            for container in deployment["spec"]["template"]["spec"]["containers"]
        )

    ui_resources = list(
        yaml.safe_load_all((content_root / "manifests" / "solution-ui.yaml").read_text())
    )
    ui_deployment = next(resource for resource in ui_resources if resource["kind"] == "Deployment")
    assert (
        ui_deployment["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"]
        == "512Mi"
    )


def test_agent_201_uses_the_workshop_certified_tool_model():
    catalog = yaml.safe_load((ROOT / "catalog/intel-xeon6-agent-201/catalog-item.yaml").read_text())

    assert catalog["metadata"]["required_models"] == ["granite-3.2-8b-tools"]


def test_agent_201_uses_three_pods_by_colocating_agent_and_tools():
    content_root = ROOT / "content-intel-xeon6-agent-201"
    catalog = yaml.safe_load((ROOT / "catalog/intel-xeon6-agent-201/catalog-item.yaml").read_text())
    agent_resources = list(
        yaml.safe_load_all((content_root / "manifests/solution-agent.yaml").read_text())
    )
    tools_resources = list(
        yaml.safe_load_all((content_root / "manifests/solution-tools.yaml").read_text())
    )
    agent_deployment = next(
        resource for resource in agent_resources if resource["kind"] == "Deployment"
    )
    containers = agent_deployment["spec"]["template"]["spec"]["containers"]
    tools_service = next(
        resource for resource in tools_resources if resource["kind"] == "Service"
    )
    pages = content_root / "modules/ROOT/pages"
    guide = "\n".join(path.read_text() for path in sorted(pages.glob("*.adoc")))

    assert catalog["metadata"]["seat_pods"] == 3
    assert [container["name"] for container in containers] == [
        "solution-agent",
        "solution-tools",
    ]
    assert all("@sha256:" in container["image"] for container in containers)
    assert not any(resource["kind"] == "Deployment" for resource in tools_resources)
    assert tools_service["spec"]["selector"] == {
        "launchpad.redhat.com/solution-stack": "agent-201"
    }
    assert "oc rollout status deploy/solution-tools" not in guide
    assert "All 2 workload pods running" in guide
    assert "Yes -- 3 pods" not in guide
    assert "Yes -- 2 workload pods" in guide
    assert "Inspect the deployed agent" in guide


def test_agent_201_remote_certification_driver_understands_colocated_tools():
    driver = (ROOT / "scripts/certify-agent-201-remote-seat.sh").read_text()

    assert "/www/modules/02-deploy-tools.html" in driver
    assert "--containers=solution-agent" in driver
    assert "for deployment in solution-agent solution-ui" in driver
    assert "for deployment in solution-tools solution-agent solution-ui" not in driver


def test_agent_201_runtime_bounds_cpu_generation_for_workshop_scale():
    containerfile = (ROOT / "workshop-images/solution-agent/Containerfile").read_text()
    build_config = (ROOT / "deploy/launchpad/overlays/arena/buildconfig.yaml").read_text()
    manifest = (ROOT / "content-intel-xeon6-agent-201/manifests/solution-agent.yaml").read_text()

    assert "triforce-solution-agent@sha256:" in containerfile
    assert "REQUIREMENTS_MAX_TOKENS" in containerfile
    assert "BRIEF_MAX_TOKENS" in containerfile
    assert '"192"' in containerfile
    assert '"512"' in containerfile
    assert "name: solution-agent-workshop" in build_config
    assert "contextDir: workshop-images/solution-agent" in build_config
    assert "REQUIREMENTS_MAX_TOKENS" in manifest
    assert "BRIEF_MAX_TOKENS" in manifest
    assert "REQUESTS_CA_BUNDLE" in manifest
    assert "SSL_CERT_FILE" in manifest
    assert "launchpad-model-ca-bundle" in manifest


def test_agentops_showroom_is_native_launchpad_content():
    playbook_path = ROOT / "site-agentops-observability.yml"
    content_root = ROOT / "content-agentops-observability"

    assert playbook_path.exists()
    playbook = yaml.safe_load(playbook_path.read_text())
    assert playbook["content"]["sources"] == [
        {"url": ".", "start_path": "content-agentops-observability"}
    ]
    assert "releases/download/patternfly-6/" in playbook["ui"]["bundle"]["url"]
    assert "releases/download/latest/" not in playbook["ui"]["bundle"]["url"]

    component = yaml.safe_load((content_root / "antora.yml").read_text())
    attributes = component["asciidoc"]["attributes"]
    assert attributes["project_name"] == "%namespace%"
    assert attributes["user_project"] == "%namespace%"
    assert attributes["maas_model"] == "%maas_model%"
    assert attributes["maas_endpoint"] == "%maas_endpoint%"
    assert attributes["cluster_display_name"] == "%cluster_display_name%"
    assert "password" not in attributes

    pages = content_root / "modules/ROOT/pages"
    content = "\n".join(path.read_text() for path in sorted(pages.glob("*.adoc")))
    for forbidden in (
        "qwen3-14b",
        "wksp-user1",
        "-u {user} -p {password}",
        "*Password:* `{password}`",
        "refs/heads/main/evaluations",
    ):
        assert forbidden not in content
    assert "Launchpad has already authenticated this terminal" in content
    assert "granite-3.2-8b-tools" in content


def test_agentops_showroom_references_only_packaged_pages_and_images():
    content_root = ROOT / "content-agentops-observability/modules/ROOT"
    nav = (content_root / "nav.adoc").read_text()
    page_names = set(re.findall(r"xref:([^#\[]+)", nav))
    assert page_names
    for page_name in page_names:
        assert (content_root / "pages" / page_name).is_file(), page_name

    for page in (content_root / "pages").glob("*.adoc"):
        for image_name in re.findall(r"image::([^\[]+)\[", page.read_text()):
            assert (content_root / "assets/images" / image_name).is_file(), (
                page.name,
                image_name,
            )


def test_agentops_showroom_records_immutable_upstream_provenance():
    provenance = (ROOT / "content-agentops-observability/UPSTREAM.md").read_text()

    assert "https://github.com/rhpds/agentops-intel-showroom" in provenance
    assert "f1881c61de55ebf5640c27e76469f4efe458edaf" in provenance
    assert "Launchpad adaptations" in provenance


def test_cpu_serving_content_uses_route_name_that_fits_launchpad_namespace():
    pages = ROOT / "content-intel-llm-cpu-serving/modules/ROOT/pages"
    content = "\n".join(path.read_text() for path in sorted(pages.glob("*.adoc")))

    assert "oc create route edge rag --service=anythingllm" in content
    assert "haproxy.router.openshift.io/timeout=120s" in content
    assert "oc get route rag" in content
    assert "oc get route anythingllm" not in content
    assert (
        'export ANYTHINGLLM_URL="https://$(oc get route rag -n {project_name} '
        '-o custom-columns=HOST:.spec.host --no-headers)"'
    ) in content
    assert "jsonpath=" not in content


def test_cpu_serving_uses_pinned_openshift_compatible_workbench_image():
    page = (
        ROOT / "content-intel-llm-cpu-serving/modules/ROOT/pages/04-wire-rag-frontend.adoc"
    ).read_text()
    containerfile = (
        ROOT / "workshop-images/anythingllm-openshift/Containerfile"
    ).read_text()
    build_config = (ROOT / "deploy/launchpad/overlays/arena/buildconfig.yaml").read_text()

    assert "anything-llm:latest" not in page
    assert (
        "partner-ai-launchpad/anythingllm-openshift@sha256:"
        "141c3a75bc565c81820bb819e18d495b123ccf9f2bfa133fdd59b58b85660807" in page
    )
    assert "STORAGE_DIR" in page
    assert "DISABLE_TELEMETRY" in page
    assert "LLM_PROVIDER: generic-openai" in page
    assert "LLM_PROVIDER: genericOpenAi" not in page
    assert "--timeout=300s" in page
    assert page.count('httpGet:') >= 2
    assert page.count('path: "/api/ping"') >= 2
    assert "tcpSocket:" not in page
    assert 'curl -fsS http://anythingllm:3001/api/ping' in page
    assert (
        "ghcr.io/mintplex-labs/anything-llm@sha256:"
        "e7751e8e65f470506379dbc2059d6a4c61eb3f22de58c184aef536a42bdd8335" in containerfile
    )
    assert "chgrp -R 0 /app" in containerfile
    assert "rm -rf /app/server/node_modules/.prisma/client" in containerfile
    assert "name: anythingllm-openshift" in build_config


def test_cpu_serving_workbench_is_embeddable_only_by_its_seat_showroom():
    page = (
        ROOT / "content-intel-llm-cpu-serving/modules/ROOT/pages/04-wire-rag-frontend.adoc"
    ).read_text()
    seat_driver = (ROOT / "scripts/certify-cpu-serving-seat.sh").read_text()
    containerfile = (ROOT / "workshop-images/anythingllm-openshift/Containerfile").read_text()
    frame_patch = (
        ROOT / "workshop-images/anythingllm-openshift/patch-frame-policy.js"
    ).read_text()
    rag_certifier = (ROOT / "scripts/certify-cpu-serving-rag.sh").read_text()

    expected_origin = (
        "https://showroom-{project_name}.{openshift_cluster_ingress_domain}"
    )
    assert "LAUNCHPAD_FRAME_ANCESTOR" in page
    assert expected_origin in page
    assert 'name: "LAUNCHPAD_FRAME_ANCESTOR"' in seat_driver
    assert '"https://showroom-${namespace}.${apps_domain}"' in seat_driver
    assert "patch-frame-policy.js" in containerfile
    assert "Content-Security-Policy" in frame_patch
    assert "frame-ancestors 'self'" in frame_patch
    assert "app.use((_, response, next)" in frame_patch
    assert "X-Frame-Options" in frame_patch
    assert '"DENY"' in frame_patch
    assert "LAUNCHPAD_FRAME_ANCESTOR" in rag_certifier
    assert "Unexpected X-Frame-Options" in rag_certifier
    assert "RAG Assistant does not allow its Showroom origin" in rag_certifier


def test_cpu_serving_catalog_uses_current_immutable_showroom_revision():
    catalog = yaml.safe_load(
        (ROOT / "catalog/intel-llm-cpu-serving/catalog-item.yaml").read_text()
    )

    assert catalog["version"] == "1.0.6"
    assert catalog["metadata"]["showroom_content_ref"] == (
        "pilot-2026-09-17-showroom-execute-v1.0.1"
    )


def test_cpu_serving_showroom_waits_for_the_external_route_to_be_ready():
    page = (
        ROOT / "content-intel-llm-cpu-serving/modules/ROOT/pages/04-wire-rag-frontend.adoc"
    ).read_text()

    assert "Wait for the Pod and Route" in page
    assert "curl -ksS -o /dev/null -w '%{http_code}'" in page
    assert '"$ANYTHINGLLM_URL/api/ping"' in page
    assert "for attempt in {1..40}" in page
    assert "OpenShift safely coalesces ingress updates" in page


def test_cpu_serving_guides_participants_to_a_rag_workspace_not_agent_admin():
    page = (
        ROOT / "content-intel-llm-cpu-serving/modules/ROOT/pages/04-wire-rag-frontend.adoc"
    ).read_text()

    assert "Create a workspace -- not an AnythingLLM agent" in page
    assert "Do not use *Admin -> Agent Skills*" in page
    assert "No MCP servers found" in page
    assert "Create Workspace" in page


def test_cpu_serving_terminal_uses_namespace_service_for_anythingllm_api():
    pages = ROOT / "content-intel-llm-cpu-serving/modules/ROOT/pages"
    load_documents = (pages / "05-load-documents.adoc").read_text()
    query_rag = (pages / "06-query-with-rag.adoc").read_text()
    terminal_exercises = load_documents + query_rag

    assert 'export ANYTHINGLLM_API_URL="http://anythingllm:3001"' in load_documents
    assert 'curl -fsS "${ANYTHINGLLM_API_URL}/api/ping"' in load_documents
    assert "ANYTHINGLLM_URL\\}/api/v1" not in terminal_exercises
    assert terminal_exercises.count("ANYTHINGLLM_API_URL\\}/api/v1") == 7
    assert "The browser Route is not used for terminal API calls" in load_documents


def test_tool_calling_hardware_story_respects_participant_rbac_boundary():
    page = (
        ROOT / "content-intel-llm-tool-calling/modules/ROOT/pages/07-intel-story.adoc"
    ).read_text()

    assert "oc get nodes" not in page
    assert "{cluster_display_name}" in page
    assert "namespace-scoped" in page
