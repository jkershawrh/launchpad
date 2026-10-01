from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "catalog/intel-llm-cpu-serving/catalog-item.yaml"
INTAKE_PATH = ROOT / "catalog-onboarding/intel-llm-cpu-serving.yaml"
OVERLAY_PATH = ROOT / (
    "deploy/launchpad/overlays/flightpath-candidate/"
    "intel-llm-cpu-serving.catalog-item.yaml"
)
CERTIFICATION_PATH = ROOT / "certification/catalog/intel-llm-cpu-serving.yaml"
CONTENT_ROOT = ROOT / "content-intel-llm-cpu-serving/modules/ROOT/pages"

CONTENT_REVISION = "1ed487299f043a89660916c9ce8a8ae5a155d6e3"
WORKLOAD_REVISION = "88867e14b1eede7d9aa563069aa093c122a4a53a"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_cpu_serving_exact_sources_are_consistent_across_candidate_surfaces() -> None:
    catalog = _load(CATALOG_PATH)
    intake = _load(INTAKE_PATH)
    overlay = _load(OVERLAY_PATH)

    assert catalog["version"] == intake["catalog"]["version"] == overlay["version"]
    assert catalog["metadata"]["showroom_content_ref"] == CONTENT_REVISION
    assert intake["sources"]["showroom"]["revision"] == CONTENT_REVISION
    assert overlay["metadata"]["showroom_content_ref"] == CONTENT_REVISION
    assert catalog["metadata"]["source_content_revision"] == CONTENT_REVISION
    assert overlay["metadata"]["source_content_revision"] == CONTENT_REVISION
    assert catalog["metadata"]["workload_revision"] == WORKLOAD_REVISION
    assert intake["sources"]["workload"]["revision"] == WORKLOAD_REVISION
    assert overlay["metadata"]["workload_revision"] == WORKLOAD_REVISION
    assert overlay["metadata"]["showroom_content_repo_url"] == (
        "https://github.com/jkershawrh/launchpad.git"
    )
    assert overlay["metadata"]["source_content_repo"] == (
        "https://github.com/jkershawrh/launchpad.git"
    )


def test_cpu_serving_declares_all_participant_operators() -> None:
    catalog = _load(CATALOG_PATH)
    intake = _load(INTAKE_PATH)
    overlay = _load(OVERLAY_PATH)
    expected_ids = ["terminal", "workspace", "openshift-console"]

    assert [tab["id"] for tab in intake["runtime"]["tabs"]] == expected_ids
    assert [tab["id"] for tab in catalog["metadata"]["showroom_tabs"]] == expected_ids
    assert [tab["id"] for tab in overlay["metadata"]["showroom_tabs"]] == expected_ids
    assert catalog["metadata"]["workspace_title"] == "RAG Assistant"
    assert overlay["metadata"]["workspace_title"] == "RAG Assistant"


def test_cpu_serving_participant_commands_match_current_anythingllm_contract() -> None:
    index = (CONTENT_ROOT / "index.adoc").read_text(encoding="utf-8")
    wire = (CONTENT_ROOT / "04-wire-rag-frontend.adoc").read_text(encoding="utf-8")
    load = (CONTENT_ROOT / "05-load-documents.adoc").read_text(encoding="utf-8")
    model_api = (CONTENT_ROOT / "03-query-the-model.adoc").read_text(encoding="utf-8")
    query = (CONTENT_ROOT / "06-query-with-rag.adoc").read_text(encoding="utf-8")
    conclusion = (CONTENT_ROOT / "08-conclusion.adoc").read_text(encoding="utf-8")
    corpus = "\n".join((index, model_api, wire, load, query, conclusion))

    assert "Show → Learn → Do → Prove" in index
    assert 'curl -fsS "${MAAS_ENDPOINT}/v1/chat/completions"' in index
    assert '"model": "{maas_model}"' in model_api
    assert '"model": "granite-2b-cpu"' not in model_api
    assert "curl -k" not in corpus
    assert "curl -sk" not in corpus
    assert "curl -ks" not in corpus
    assert "/api/v1/document/create-link" not in corpus
    assert load.count("/api/v1/document/upload-link") == 2
    assert load.count('["documents"][0]["location"]') == 2
    assert 'export ANYTHINGLLM_API_KEY="your-api-key-here"' in load
    assert 'export ANYTHINGLLM_API_URL="http://anythingllm:3001"' in load
    assert "OpenShift Console Checkpoint" in wire
    assert "Open the *RAG Assistant* tab inside *Open Lab*" in wire
    assert "oc delete pvc anythingllm-storage" in conclusion
    assert "Launchpad subsequently reclaims the complete seat namespace" in conclusion


def test_cpu_serving_certification_records_managed_model_identity() -> None:
    certifier = (ROOT / "scripts/certify-cpu-serving-catalog-seat.sh").read_text(
        encoding="utf-8"
    )
    contract = _load(CERTIFICATION_PATH)
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    expected = {(item["path"], item.get("equals")) for item in assertions}

    assert "stage=\"managed-model-proof\"" in certifier
    assert "observed_model" in certifier
    assert "answer_present" in certifier
    assert "configured_model" in certifier
    assert "curl -k" not in certifier
    assert "curl -sk" not in certifier
    assert "curl -ks" not in certifier
    assert 'api_key="$(' not in certifier
    assert 'key="$(oc get secret launchpad-participant-runtime' in certifier
    assert "exec -i -n" in certifier
    assert ("model_journey.answer_present", True) in expected
    assert ("model_journey.identity_present", True) in expected
    assert ("model_journey.configured_model", "granite-3.2-8b-tools") in expected
    assert ("model_journey.observed_model", "granite-3.2-8b-tools") in expected
    assert ("rag_journey.model_participated", True) in expected
    assert ("rag_journey.model", "granite-3.2-8b-tools") in expected
    assert ("operator_journey.console_url_present", True) in expected
    assert ("operator_journey.console_namespace_scope", True) in expected


def test_cpu_serving_orderability_does_not_transfer_from_the_prior_contract() -> None:
    catalog = _load(CATALOG_PATH)
    intake = _load(INTAKE_PATH)
    overlay = _load(OVERLAY_PATH)

    # v1.0.12 proof cannot bind the revised v1.0.13 participant journey.
    assert catalog["version"] == intake["catalog"]["version"] == (
        "1.0.13-flightpath.1"
    )
    assert catalog["status"] == intake["catalog"]["status"] == "draft"
    assert overlay["status"] == "draft"
    assert catalog["metadata"]["certification_stage"] == "source-reviewed"
    assert intake["certification"]["stage"] == "source-reviewed"
    assert overlay["metadata"]["certification_stage"] == "source-reviewed"
    assert catalog["metadata"]["max_workshop_seats"] == 1
    assert intake["certification"]["max_workshop_seats"] == 1
    assert overlay["metadata"]["max_workshop_seats"] == 1
    assert catalog["metadata"]["certification_transfer"] == "none"
    assert intake["learning"]["certification_transfer"] == "none"
    assert catalog["metadata"]["activation_blockers"] == [
        "Publish and pin the exact strict-TLS v1.0.13 content and certification driver revision.",
        "Recertify one Flightpath seat for managed-model and AnythingLLM RAG participation, Console and Terminal scope, cleanup, credential revocation, and zero residue.",
    ]
    assert catalog["metadata"]["activation_blockers"] == intake["certification"][
        "activation_blockers"
    ]
