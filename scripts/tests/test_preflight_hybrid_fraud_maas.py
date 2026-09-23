import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/preflight_hybrid_fraud_maas.py"


def _module():
    spec = importlib.util.spec_from_file_location("fraud_maas_preflight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _runner(*, ready: bool):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        tail = args[2:]
        if tail == ["whoami", "--show-server"]:
            return CompletedProcess(args, 0, "https://api.arena.fm2aihpcsed.com:6443\n", "")
        if tail[:2] == ["get", "crd"]:
            missing_kuadrant = not ready and tail[2] == "kuadrants.kuadrant.io"
            return CompletedProcess(args, 1 if missing_kuadrant else 0, "" if missing_kuadrant else "crd\n", "")
        if tail[:3] == ["get", "kuadrant", "kuadrant"]:
            return CompletedProcess(args, 0 if ready else 1, json.dumps({"status": {"conditions": [{"type": "Ready", "status": "True"}]}}) if ready else "", "private-error")
        if tail[:2] == ["get", "datasciencecluster"]:
            state = "Managed" if ready else "Removed"
            return CompletedProcess(args, 0, json.dumps({"items": [{"spec": {"components": {"aigateway": {"modelsAsAService": {"managementState": state}}}}}]}), "")
        if tail[:2] == ["get", "subscription"]:
            items = [{"spec": {"name": "rhcl-operator", "channel": "stable"}}] if ready else []
            return CompletedProcess(args, 0, json.dumps({"items": items}), "")
        if tail[:3] == ["get", "maastenantconfig", "default-tenant"]:
            return CompletedProcess(args, 0 if ready else 1, json.dumps({"status": {"infraNamespace": "redhat-ai-gateway-infra", "conditions": [{"type": "Ready", "status": "True"}]}}) if ready else "", "private-error")
        if tail[:3] == ["get", "aitenant", "models-as-a-service"]:
            return CompletedProcess(args, 0 if ready else 1, json.dumps({"status": {"conditions": [{"type": "Ready", "status": "True"}]}}) if ready else "", "private-error")
        if tail[:3] == ["get", "secret", "maas-db-config"]:
            assert tail[3:5] == ["-n", "redhat-ai-gateway-infra"]
            return CompletedProcess(args, 0, "secret\n", "")
        if tail[:3] == ["get", "authorino", "authorino"]:
            return CompletedProcess(args, 0 if ready else 1, json.dumps({"spec": {"listener": {"tls": {"enabled": True}}}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}) if ready else "", "private-error")
        if tail[:3] == ["get", "gateway", "maas-default-gateway"]:
            return CompletedProcess(args, 0 if ready else 1, json.dumps({"metadata": {"annotations": {"security.opendatahub.io/authorino-tls-bootstrap": "true"}}, "status": {"conditions": [{"type": "Programmed", "status": "True"}]}}) if ready else "", "private-error")
        if tail[:3] == ["get", "deployment", "maas-api"]:
            return CompletedProcess(args, 0 if ready else 1, json.dumps({"status": {"readyReplicas": 1}}) if ready else "", "private-error")
        raise AssertionError(tail)

    return run, calls


def test_missing_shared_maas_prerequisites_are_red_without_leaking_provider_output():
    module = _module()
    runner, calls = _runner(ready=False)

    report = module.review("/isolated/arena", runner=runner)

    assert report["status"] == "RED"
    assert report["findings"] == [
        "maas-authorino-not-ready",
        "maas-component-disabled",
        "maas-connectivity-link-subscription-missing",
        "maas-gateway-not-ready",
        "maas-infra-namespace-unresolved",
        "maas-kuadrant-instance-not-ready",
        "maas-kuadrant-operator-missing",
        "maas-tenant-unavailable",
    ]
    assert report["mutation_performed"] is False
    assert report["release_eligible"] is False
    assert "private-error" not in str(report)
    assert all(args[2] in {"whoami", "get"} for args in calls)
    assert not any(args[2:5] == ["get", "secret", "maas-db-config"] for args in calls)


def test_ready_prerequisites_only_allow_candidate_configuration_not_release():
    module = _module()
    runner, _calls = _runner(ready=True)

    report = module.review("/isolated/arena", runner=runner)

    assert report["status"] == "ready-for-candidate-configuration"
    assert report["findings"] == []
    assert report["release_eligible"] is False


def test_wrong_cluster_fails_before_any_resource_read():
    module = _module()
    calls = []

    def wrong_server(args, **kwargs):
        calls.append(args)
        return CompletedProcess(args, 0, "https://api.other.invalid:6443\n", "")

    report = module.review("/isolated/arena", runner=wrong_server)

    assert report["findings"] == ["arena-context-unavailable"]
    assert len(calls) == 1
