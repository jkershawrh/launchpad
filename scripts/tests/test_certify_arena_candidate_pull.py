import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/certify_arena_candidate_pull.py"
IMAGE = "ghcr.io/jkershawrh/hybrid-fraud-detection@sha256:" + "a" * 64
CONTEXT = "default/api-arena-fm2aihpcsed-com:6443/kube:admin"


def _module():
    spec = importlib.util.spec_from_file_location("arena_pull", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_dry_run_makes_no_cluster_calls() -> None:
    module = _module()

    def forbidden(*args, **kwargs):
        raise AssertionError("dry run must not contact a cluster")

    report = module.probe(IMAGE, CONTEXT, execute=False, runner=forbidden)

    assert report["status"] == "planned"
    assert report["cluster"] == "arena"
    assert report["release_eligible"] is False


def test_wrong_server_or_unauthorized_context_fails_before_mutation() -> None:
    module = _module()
    calls = []

    def wrong_server(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, "https://api.brutus.fm2aihpcsed.com:6443\n", "")

    wrong = module.probe(IMAGE, CONTEXT, execute=True, runner=wrong_server)
    assert wrong["status"] == "blocked"
    assert wrong["findings"] == ["arena-server-mismatch"]
    assert len(calls) == 1

    def unauthorized(command, **kwargs):
        calls.append(command)
        if "--show-server" in command:
            return CompletedProcess(command, 0, module.ARENA_SERVER + "\n", "")
        return CompletedProcess(command, 1, "", "Unauthorized")

    calls.clear()
    denied = module.probe(IMAGE, CONTEXT, execute=True, runner=unauthorized)
    assert denied["status"] == "blocked"
    assert denied["findings"] == ["arena-auth-unavailable"]
    assert all("create" not in command for command in calls)


def test_successful_probe_uses_only_target_context_and_cleans_its_namespace() -> None:
    module = _module()
    calls = []
    namespace = "launchpad-image-cert-12345678"
    uid = "namespace-uid"

    def runner(command, **kwargs):
        calls.append((command, kwargs.get("input")))
        if "--show-server" in command:
            return CompletedProcess(command, 0, module.ARENA_SERVER + "\n", "")
        if "whoami" in command:
            return CompletedProcess(command, 0, "kube:admin\n", "")
        if "create" in command and "Namespace" in (kwargs.get("input") or ""):
            return CompletedProcess(command, 0, json.dumps({"metadata": {"uid": uid}}), "")
        if "create" in command:
            pod = json.loads(kwargs["input"])
            assert pod["spec"]["containers"][0]["imagePullPolicy"] == "Always"
            assert pod["metadata"]["namespace"] == namespace
            return CompletedProcess(command, 0, "{}", "")
        if "get" in command and "pod" in command:
            return CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "status": {
                            "phase": "Succeeded",
                            "containerStatuses": [{"imageID": "docker-pullable://" + IMAGE}],
                        }
                    }
                ),
                "",
            )
        if "get" in command and "namespace" in command:
            return CompletedProcess(command, 0, json.dumps({"metadata": {"uid": uid}}), "")
        if "delete" in command:
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    report = module.probe(
        IMAGE,
        CONTEXT,
        execute=True,
        runner=runner,
        namespace_suffix="12345678",
        sleeper=lambda seconds: None,
    )

    assert report["status"] == "passed"
    assert report["namespace"] == namespace
    assert report["cleanup"] == "passed"
    assert report["release_eligible"] is False
    assert all(command[:2] == ["oc", f"--context={CONTEXT}"] for command, _ in calls)
    assert any("delete" in command for command, _ in calls)


def test_invalid_image_or_namespace_suffix_fails_without_cluster_calls() -> None:
    module = _module()

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid input must not contact a cluster")

    for image, suffix in (("ghcr.io/x/app:latest", "12345678"), (IMAGE, "bad/name")):
        report = module.probe(
            image, CONTEXT, execute=True, runner=forbidden, namespace_suffix=suffix
        )
        assert report["status"] == "blocked"


def test_failed_pod_creation_still_reclaims_only_the_created_namespace() -> None:
    module = _module()
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "--show-server" in command:
            return CompletedProcess(command, 0, module.ARENA_SERVER, "")
        if "whoami" in command:
            return CompletedProcess(command, 0, "kube:admin", "")
        if "create" in command and "Namespace" in (kwargs.get("input") or ""):
            return CompletedProcess(command, 0, '{"metadata":{"uid":"owned-uid"}}', "")
        if "create" in command:
            return CompletedProcess(command, 1, "", "rejected")
        if "get" in command and "namespace" in command:
            return CompletedProcess(command, 0, '{"metadata":{"uid":"owned-uid"}}', "")
        if "delete" in command:
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    report = module.probe(IMAGE, CONTEXT, execute=True, runner=runner, namespace_suffix="12345678")

    assert report["status"] == "blocked"
    assert report["findings"] == ["pod-create-failed"]
    assert report["cleanup"] == "passed"
    assert any("delete" in command for command in calls)


def test_namespace_uid_change_prevents_deletion() -> None:
    module = _module()
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "--show-server" in command:
            return CompletedProcess(command, 0, module.ARENA_SERVER, "")
        if "whoami" in command:
            return CompletedProcess(command, 0, "kube:admin", "")
        if "create" in command and "Namespace" in (kwargs.get("input") or ""):
            return CompletedProcess(command, 0, '{"metadata":{"uid":"owned-uid"}}', "")
        if "create" in command:
            return CompletedProcess(command, 1, "", "rejected")
        if "get" in command and "namespace" in command:
            return CompletedProcess(command, 0, '{"metadata":{"uid":"different-uid"}}', "")
        raise AssertionError(command)

    report = module.probe(IMAGE, CONTEXT, execute=True, runner=runner, namespace_suffix="12345678")

    assert report["status"] == "blocked"
    assert "namespace-cleanup-unverified" in report["findings"]
    assert report["cleanup"] == "failed"
    assert not any("delete" in command for command in calls)
