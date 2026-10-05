from pathlib import Path

import yaml


from app.services.catalog_onboarding import load_intake


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts/certify-agent-201-via-control-plane.py"
CATALOG_SEAT_PROBE = ROOT / "scripts/certify-agent-201-catalog-seat.sh"
CATALOG = ROOT / "catalog/intel-xeon6-agent-201/catalog-item.yaml"
INTAKE = ROOT / "catalog-onboarding/intel-xeon6-agent-201.yaml"
CERTIFICATION = ROOT / "certification/catalog/intel-xeon6-agent-201.yaml"

SOURCE_REVISION = "11e209450b798678d78c8964407106f5475aca33"
HISTORICAL_CERTIFIED_SOURCE_REVISION = "b8475464e5f1447da67ccfc0673b9a8a3e4757d7"
WORKLOAD_REVISION = "f484cb66c3dcddff323df8814f637dc92c73c179"
WORKLOAD_BASE = (
    "https://raw.githubusercontent.com/rhpds/triforce/"
    f"{WORKLOAD_REVISION}/infrastructure/manifests-201"
)
RUNTIME_IMAGES = {
    "solution-tools": "quay.io/redhat-gpte/triforce-solution-tools@sha256:856874dc984eeb05ec0aeadb6f49265a58687eed17e5a92bc769875d3df44850",
    "solution-agent": "ghcr.io/jkershawrh/triforce-solution-agent@sha256:fbe9c2dacb203346e89257aaf097a35bd0e741fe8ddbbc8fea72f4e547961e67",
    "solution-ui": "quay.io/redhat-gpte/triforce-solution-ui@sha256:9388d91c19e845b8dcee12ef9037e4b93afadea4df5e7912dbe0a6151b8605fb",
}


def test_remote_certifier_uses_persisted_cluster_client_without_kubeconfig_or_exec():
    source = DRIVER.read_text()

    assert 'service._target_clients(args.cluster_id)' in source
    assert "create_namespaced_pod" in source
    assert "read_namespaced_pod_log" in source
    assert 'service_account_name="showroom"' in source
    assert "connect_get_namespaced_pod_exec" not in source
    assert "KUBECONFIG" not in source
    assert "config.load_kube_config" not in source


def test_remote_certifier_runs_the_documented_agent_201_journey():
    source = DRIVER.read_text()

    for expected in (
        "intel_hardware_lookup",
        "openshift_capabilities",
        "reference_architectures",
        "solution-agent",
        "solution-ui",
        "ADVISOR_MODEL",
    ):
        assert expected in source

    assert "https://raw.githubusercontent.com/jkershawrh/launchpad/" in source
    assert "9526ede61b5c31949f3a1bedd133b5a17e554178/" in source
    assert "content-intel-xeon6-agent-201/manifests" in source


def test_remote_certifier_proves_participant_scope_and_sanitizes_evidence():
    source = DRIVER.read_text()

    assert "ast.literal_eval(output)" in source
    assert '"failure_stage"' in source
    assert "tools_health" in source
    assert "model_request" in source
    assert 'oc project "$NAMESPACE"' not in source
    assert source.count('-n "$NAMESPACE"') >= 8
    assert "cross_namespace_read_denied" in source
    assert "node_list_denied" in source
    assert '"contains_plaintext_credentials": False' in source
    assert "MAAS_API_KEY}" not in source


def test_catalog_seat_probe_reports_bounded_failure_stages():
    source = CATALOG_SEAT_PROBE.read_text()

    for stage in (
        "route-discovery",
        "tools-health",
        "agent-health",
        "app-health",
        "tools-contract",
        "model-request",
        "response-contract",
        "response-brief",
        "response-requirements",
        "response-hardware-options",
        "response-platform-capabilities",
        "response-architecture",
        "response-inference-errors",
        "response-hardware-tool",
        "response-platform-tool",
        "response-architecture-tool",
    ):
        assert f'stage="{stage}"' in source
    assert "semantic_response=brief_type:" in source
    assert "brief_length:" in source
    assert "top_level_keys:" in source
    assert "inference_error_count:" in source
    assert "inference_http_statuses:" in source
    assert "curl -k" not in source
    assert "curl_options=(-fsSk" not in source
    assert 'deployment/showroom' in source
    assert 'http://solution-agent:8082/api/v1/advise' in source
    assert 'https://${agent_host}/api/v1/advise' not in source


def test_remote_certifier_reads_model_connection_from_participant_runtime_secret():
    source = (ROOT / "scripts/certify-agent-201-remote-seat.sh").read_text()
    assert "launchpad-participant-runtime" in source
    assert ".data.MAAS_ENDPOINT" in source
    assert ".data.MAAS_MODEL" in source
    assert "/www/modules/03-wire-agent.html" not in source


def test_agent_201_catalog_pins_the_reviewed_source_and_resolved_workload():
    intake = load_intake(INTAKE)
    catalog = yaml.safe_load(CATALOG.read_text())

    assert intake["sources"]["showroom"] == {
        "repo_url": "https://github.com/jkershawrh/intel-xeon6-ai-agent-201.git",
        "revision": SOURCE_REVISION,
        "playbook": "site.yml",
        "start_path": ".",
    }
    assert intake["sources"]["workload"]["revision"] == WORKLOAD_REVISION
    assert intake["catalog"]["status"] == "active"
    assert intake["certification"]["stage"] == "1-seat-certified"
    assert intake["certification"]["certified_seats"] == 1
    assert intake["certification"]["promotion_sequence"] == [1]
    assert intake["certification"]["activation_blockers"] == []
    assert all(
        "mutable workload tag" not in blocker
        for blocker in intake["certification"]["activation_blockers"]
    )

    metadata = catalog["metadata"]
    assert metadata["showroom_content_repo_url"] == intake["sources"]["showroom"]["repo_url"]
    assert metadata["showroom_content_ref"] == SOURCE_REVISION
    assert metadata["showroom_content_playbook"] == "site.yml"
    assert metadata["source_content_revision"] == SOURCE_REVISION
    assert metadata["workload_revision"] == WORKLOAD_REVISION
    assert metadata["certification_stage"] == "1-seat-certified"


def test_agent_201_catalog_and_source_expose_the_three_operator_tabs():
    intake = load_intake(INTAKE)
    assert intake["runtime"]["workload"]["routes"] == {"workspace": "app"}
    assert intake["runtime"]["tabs"] == [
        {"id": "terminal", "title": "Terminal", "source": "showroom.terminal"},
        {
            "id": "workspace",
            "title": "Solution Architect",
            "source": "workload.route.workspace",
            "same_origin_path": "/workspace/",
            "rewrite_target": "/",
            "proxy_paths": [{"path": "/api/v1"}],
        },
        {
            "id": "openshift-console",
            "title": "OpenShift Console",
            "source": "cluster.console_url",
        },
    ]


def test_agent_201_certification_fails_closed_on_inference_identity_and_exports_proof():
    contract = yaml.safe_load(CERTIFICATION.read_text())
    assert [profile["seats"] for profile in contract["spec"]["scale_profiles"]] == [1]
    assertions = contract["spec"]["seat_probe"]["json_assertions"]

    for assertion in (
        {"path": "intel_xeon_inference.configured_model", "equals": "granite-3.2-8b-tools"},
        {"path": "intel_xeon_inference.model_participated", "equals": True},
        {"path": "intel_xeon_inference.matches_configured_model", "equals": True},
        {"path": "proof_export.tool_count", "equals": 3},
        {"path": "proof_export.contains_sensitive_values", "equals": False},
        {"path": "provenance.showroom_revision", "equals": SOURCE_REVISION},
        {"path": "provenance.workload_revision", "equals": WORKLOAD_REVISION},
        {"path": "runtime_images.solution_tools", "equals": RUNTIME_IMAGES["solution-tools"]},
        {"path": "runtime_images.solution_agent", "equals": RUNTIME_IMAGES["solution-agent"]},
        {"path": "runtime_images.solution_ui", "equals": RUNTIME_IMAGES["solution-ui"]},
    ):
        assert assertion in assertions

    pages = {page["id"]: page for page in contract["spec"]["showroom"]["pages"]}
    assert pages["prove-and-clean"] == {
        "id": "prove-and-clean",
        "path": "/www/modules/05-prove-and-clean.html",
        "marker": "Prove and Clean Up",
    }

    source = CATALOG_SEAT_PROBE.read_text()
    assert 'stage="response-model"' in source
    assert "ADVISOR_MODEL" in source
    assert "all(. == $configured_model)" in source
    assert "response_sha256" in source
    assert WORKLOAD_BASE in source
    assert 'content-intel-xeon6-agent-201/manifests/$manifest' not in source
    for deployment, image in RUNTIME_IMAGES.items():
        assert deployment in source
        assert image in source


def test_agent_201_evidence_records_exact_candidate_live_certification():
    review = yaml.safe_load(
        (ROOT / "evidence/lab-experience-review-20260930.yaml").read_text()
    )["labs"]["intel-xeon6-agent-201"]

    assert review["overall_status"] == "one-seat-live-certified-active"
    assert (
        review["source_truth"]["candidate_revision"]
        == HISTORICAL_CERTIFIED_SOURCE_REVISION
    )
    assert review["source_truth"]["certification_transfer"] == "exact-candidate-only"
    assert review["live_certification"]["result"] == "GREEN-live"
    assert review["live_certification"]["rubric_score"] == 100
