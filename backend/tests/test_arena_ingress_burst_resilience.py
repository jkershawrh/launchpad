"""Contracts for the Arena ingress path under September participant load."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INGRESS_TUNING = ROOT / "deploy/launchpad/arena-pilot/ingresscontroller-default.yaml"
EXACT_75_DRIVER = ROOT / "scripts/certify-september-17-exact-75.sh"
SERVE_RAG_CERTIFIER = ROOT / "scripts/certify-cpu-serving-rag.sh"
SERVE_SHOWROOM = (
    ROOT / "content-intel-llm-cpu-serving/modules/ROOT/pages/04-wire-rag-frontend.adoc"
)


def test_arena_router_coalesces_route_churn_during_participant_setup():
    manifest = yaml.safe_load(INGRESS_TUNING.read_text())

    assert manifest["apiVersion"] == "operator.openshift.io/v1"
    assert manifest["kind"] == "IngressController"
    assert manifest["metadata"] == {
        "name": "default",
        "namespace": "openshift-ingress-operator",
    }
    assert manifest["spec"]["tuningOptions"]["reloadInterval"] == "30s"


def test_exact_75_driver_fails_if_router_restarts_during_the_wave():
    source = EXACT_75_DRIVER.read_text()

    assert "router_restart_total" in source
    assert 'router_restarts_before="$(router_restart_total)"' in source
    assert 'router_restarts_after="$(router_restart_total)"' in source
    assert 'router_restart_increase=$((router_restarts_after - router_restarts_before))' in source
    assert '"router_restart_increase"' in source
    assert '"$router_restart_increase" -eq 0' in source


def test_serve_llms_waits_for_the_external_route_after_reload_coalescing():
    certifier = SERVE_RAG_CERTIFIER.read_text()
    showroom = SERVE_SHOWROOM.read_text()

    assert "wait_for_route" in certifier
    assert '"${base_url}/api/ping"' in certifier
    assert "LAUNCHPAD_ROUTE_READY_ATTEMPTS" in certifier
    assert "AnythingLLM Route did not become ready" in certifier

    assert "Wait for the Pod and Route" in showroom
    assert "ANYTHINGLLM_ROUTE_STATUS" in showroom
    assert '"$ANYTHINGLLM_ROUTE_STATUS" = "200"' in showroom
