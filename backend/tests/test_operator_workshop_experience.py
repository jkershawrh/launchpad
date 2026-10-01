from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "content-operators/modules/ROOT/pages"
EXPECTED_TITLE = "OpenShift 201: Build an Operator-Managed Pipeline"
REVISION = "6fcb2906e4d22f90afe62a8304b45f04be7cd048"


def _load(path: str):
    return yaml.safe_load((ROOT / path).read_text())


def test_operator_workshop_identity_is_truthful_across_contracts():
    catalog = _load("catalog/openshift-operators-workshop/catalog-item.yaml")
    onboarding = _load("catalog-onboarding/openshift-operators-workshop.yaml")
    certification = _load("certification/catalog/openshift-operators-workshop.yaml")
    antora = _load("content-operators/antora.yml")

    assert catalog["display_name"] == EXPECTED_TITLE
    assert onboarding["catalog"]["display_name"] == EXPECTED_TITLE
    assert certification["metadata"]["display_name"] == EXPECTED_TITLE
    assert antora["title"] == EXPECTED_TITLE
    assert "AI Operator" not in "\n".join(path.read_text() for path in PAGES.glob("*.adoc"))
    assert catalog["metadata"]["showroom_content_ref"] == REVISION
    assert catalog["metadata"]["source_content_revision"] == REVISION
    assert catalog["metadata"]["workload_revision"] == REVISION
    assert onboarding["sources"]["showroom"]["revision"] == REVISION
    assert onboarding["sources"]["workload"]["revision"] == REVISION


def test_operator_workshop_requires_and_uses_openshift_pipelines():
    catalog = _load("catalog/openshift-operators-workshop/catalog-item.yaml")
    onboarding = _load("catalog-onboarding/openshift-operators-workshop.yaml")
    corpus = "\n".join(path.read_text() for path in sorted(PAGES.glob("*.adoc")))

    assert "openshift-pipelines" in catalog["required_capabilities"]
    assert catalog["metadata"]["operator_capabilities"] == ["openshift-pipelines"]
    assert "openshift-pipelines" in onboarding["runtime"]["required_capabilities"]
    assert onboarding["runtime"]["required_models"] == []
    for kind in ("Task", "Pipeline", "PipelineRun", "TaskRun"):
        assert kind in corpus
    assert "hello-openshift" not in corpus


def test_operator_workshop_is_executable_show_learn_do_prove():
    corpus = "\n".join(path.read_text() for path in sorted(PAGES.glob("*.adoc")))
    index = (PAGES / "index.adoc").read_text()
    for stage in ("== Show", "== Learn", "== Do", "== Prove"):
        assert stage in corpus
    assert "== Show → Learn → Do → Prove" in index
    assert corpus.count("role=execute") == 10
    assert "OpenShift Console" in corpus
    assert "operator-reconciled:" in corpus
    assert "Launchpad" in corpus
    assert "Showroom guide is the *Story* view" in index
    assert "*Terminal* is the authoring and proof workspace" in index
    assert "*OpenShift Console* is the integrated operator view" in index
    assert 'test "$(oc auth can-i get nodes)" = no' in index
    assert 'test "$(oc auth can-i get pods -n openshift-operators)" = no' in index


def test_operator_certification_probes_reconciliation_and_cleanup():
    contract = _load("certification/catalog/openshift-operators-workshop.yaml")
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    asserted = {(row["path"], row.get("equals")) for row in assertions}
    for expected in (
        ("operator.api_available", True),
        ("operator.api_group", "tekton.dev/v1"),
        ("operator.namespace_scoped", True),
        ("operator.run_succeeded", True),
        ("operator.result_marker", True),
        ("operator.taskrun_count", 1),
        ("operator.resources_removed", True),
        ("inference.required", False),
        ("inference.participated", False),
    ):
        assert expected in asserted

    script = (ROOT / "scripts/certify-operator-workshop-seat.sh").read_text()
    for required in (
        "apiVersion: tekton.dev/v1",
        "kind: Task",
        "kind: Pipeline",
        "kind: PipelineRun",
        "condition=Succeeded",
        "operator-reconciled:",
    ):
        assert required in script
    assert "hello-openshift" not in script
    assert "oc create deployment" not in script
    assert "MAAS_API" not in script
    assert "/chat/completions" not in script
    assert 'inference:{required:false,participated:false}' in script


def test_operator_journey_is_one_seat_live_certified_and_active():
    catalog = _load("catalog/openshift-operators-workshop/catalog-item.yaml")
    onboarding = _load("catalog-onboarding/openshift-operators-workshop.yaml")

    assert catalog["status"] == "active"
    assert catalog["metadata"]["certification_stage"] == "1-seat-certified"
    assert catalog["metadata"]["max_workshop_seats"] == 1
    assert onboarding["catalog"]["status"] == "active"
    assert onboarding["certification"]["certified_seats"] == 1
    assert onboarding["certification"]["max_workshop_seats"] == 1
    assert onboarding["certification"]["activation_blockers"] == []


def test_operator_workshop_declares_story_terminal_and_console_contracts():
    catalog = _load("catalog/openshift-operators-workshop/catalog-item.yaml")
    onboarding = _load("catalog-onboarding/openshift-operators-workshop.yaml")
    expected_tabs = [
        {"id": "terminal", "title": "Terminal", "source": "showroom.terminal"},
        {
            "id": "openshift-console",
            "title": "OpenShift Console",
            "source": "cluster.console_url",
        },
    ]

    assert catalog["metadata"]["showroom_tabs"] == expected_tabs
    assert onboarding["runtime"]["tabs"] == expected_tabs
    assert catalog["metadata"]["required_models"] == []
    assert catalog["metadata"]["inference_endpoint"] == "none"


def test_operator_review_records_the_live_certified_exact_candidate():
    review = _load("evidence/lab-experience-review-20260930.yaml")
    lab = review["labs"]["openshift-operators-workshop"]
    source_state = lab["source_state"]

    assert lab["overall_status"] == "one-seat-live-certified-active"
    assert source_state["published_revision"] == REVISION
    assert source_state["candidate_revision"] == REVISION
    assert source_state["certification_transfer"] == "green-live"
    assert lab["live_certification"]["rubric_score"] == 100
