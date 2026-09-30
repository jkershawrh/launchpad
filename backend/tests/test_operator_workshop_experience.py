from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "content-operators/modules/ROOT/pages"
EXPECTED_TITLE = "OpenShift 201: Build an Operator-Managed Pipeline"


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
    for stage in ("== Show", "== Learn", "== Do", "== Prove"):
        assert stage in corpus
    assert corpus.count("role=execute") >= 8
    assert "OpenShift Console" in corpus
    assert "operator-reconciled:" in corpus
    assert "Launchpad" in corpus


def test_operator_certification_probes_reconciliation_and_cleanup():
    contract = _load("certification/catalog/openshift-operators-workshop.yaml")
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    asserted = {(row["path"], row.get("equals")) for row in assertions}
    for expected in (
        ("operator.api_available", True),
        ("operator.run_succeeded", True),
        ("operator.result_marker", True),
        ("operator.resources_removed", True),
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


def test_changed_operator_journey_requires_fresh_one_seat_certification():
    catalog = _load("catalog/openshift-operators-workshop/catalog-item.yaml")
    onboarding = _load("catalog-onboarding/openshift-operators-workshop.yaml")

    assert catalog["status"] == "draft"
    assert catalog["metadata"]["certification_stage"] == "source-reviewed"
    assert catalog["metadata"]["max_workshop_seats"] == 1
    assert onboarding["catalog"]["status"] == "draft"
    assert onboarding["certification"]["certified_seats"] == 0
    assert onboarding["certification"]["max_workshop_seats"] == 1
    assert "fresh-one-seat-operator-certification" in onboarding["certification"]["activation_blockers"]
