import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def render(path: str) -> list[dict]:
    result = subprocess.run(
        ["oc", "kustomize", str(ROOT / path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [item for item in yaml.safe_load_all(result.stdout) if item]


def resource(items: list[dict], kind: str, name: str) -> dict:
    return next(
        item
        for item in items
        if item["kind"] == kind and item["metadata"]["name"] == name
    )


def test_arena_ha_overlay_has_two_workers_and_no_direct_reconciler() -> None:
    items = render("deploy/launchpad/overlays/arena-ha-pilot")

    config = resource(items, "ConfigMap", "launchpad-config")
    worker = resource(items, "Deployment", "lifecycle-worker")
    scheduler = resource(items, "CronJob", "lifecycle-scheduler")
    legacy = resource(items, "CronJob", "launchpad-resource-reconciler")

    assert config["data"]["LIFECYCLE_HA_ENABLED"] == "true"
    assert worker["spec"]["replicas"] == 2
    assert worker["spec"]["template"]["spec"]["topologySpreadConstraints"] == [
        {
            "maxSkew": 1,
            "topologyKey": "kubernetes.io/hostname",
            "whenUnsatisfiable": "ScheduleAnyway",
            "labelSelector": {
                "matchLabels": {
                    "app.kubernetes.io/managed-by": "kustomize",
                    "app.kubernetes.io/name": "lifecycle-worker",
                }
            },
        }
    ]
    worker_container = next(
        item
        for item in worker["spec"]["template"]["spec"]["containers"]
        if item["name"] == "lifecycle-worker"
    )
    worker_env = {item["name"]: item.get("value") for item in worker_container["env"]}
    assert worker_env["SSL_CERT_FILE"] == "/etc/launchpad-ca/ca-bundle.crt"
    assert worker_env["REQUESTS_CA_BUNDLE"] == "/etc/launchpad-ca/ca-bundle.crt"
    assert worker_env["LIFECYCLE_JOB_LEASE_SECONDS"] == "30"
    assert worker_env["LIFECYCLE_HEARTBEAT_INTERVAL_SECONDS"] == "5"
    assert worker_env["LIFECYCLE_POLL_INTERVAL_SECONDS"] == "1"
    assert scheduler["spec"]["suspend"] is False
    assert legacy["spec"]["suspend"] is True


def test_arena_model_network_policy_allows_api_and_lifecycle_workers() -> None:
    policy = yaml.safe_load(
        (ROOT / "deploy/launchpad/overlays/arena/fleet-model-access.yaml").read_text()
    )

    assert policy["metadata"]["namespace"] == "fleet-llm-d"
    control_plane_source = policy["spec"]["ingress"][0]["from"][0]
    assert control_plane_source["namespaceSelector"]["matchLabels"] == {
        "kubernetes.io/metadata.name": "partner-ai-launchpad"
    }
    assert control_plane_source["podSelector"]["matchExpressions"] == [
        {
            "key": "app.kubernetes.io/name",
            "operator": "In",
            "values": ["backend", "lifecycle-worker"],
        }
    ]


def test_flightpath_dr_overlay_is_passive_and_contains_no_credentials() -> None:
    items = render("deploy/launchpad/overlays/flightpath-dr")
    deployments = [item for item in items if item["kind"] == "Deployment"]
    cronjobs = [item for item in items if item["kind"] == "CronJob"]
    config = resource(items, "ConfigMap", "launchpad-config")

    assert deployments
    assert all(item["spec"]["replicas"] == 0 for item in deployments)
    assert all(item["spec"].get("suspend") is True for item in cronjobs)
    assert config["data"]["LAUNCHPAD_CONTROL_PLANE_ROLE"] == "standby"

    overlay_text = "\n".join(
        path.read_text()
        for path in (ROOT / "deploy/launchpad/overlays/flightpath-dr").glob("*")
        if path.is_file()
    ).lower()
    assert "kubeadmin" not in overlay_text
    assert "pass" + "word:" not in overlay_text


def test_dr_runbook_requires_fencing_before_promotion() -> None:
    runbook = " ".join(
        (ROOT / "docs/flightpath-dr-runbook.md").read_text().lower().split()
    )

    assert "fence arena" in runbook
    assert "rotate or revoke" in runbook
    assert "split-brain" in runbook
    assert "restore" in runbook
    assert "failback" in runbook
    assert "flightpath becomes the primary control plane" in runbook
    assert "arena becomes the warm control-plane standby" in runbook
    assert "execution clusters are not control-plane dr" in runbook
    assert "three consecutive" in runbook


def test_flightpath_is_registered_but_fail_closed_in_source_and_runtime() -> None:
    source = yaml.safe_load((ROOT / "config/clusters.yaml").read_text())
    source_target = next(
        item for item in source["clusters"] if item["cluster_id"] == "flightpath"
    )
    assert source_target["enabled"] is False
    assert source_target["public_access_enabled"] is False
    assert source_target["credential_secret"].endswith(
        "/launchpad-flightpath-kubeconfig"
    )

    arena_items = render("deploy/launchpad/overlays/arena")
    runtime = resource(
        arena_items, "ConfigMap", "launchpad-cluster-targets"
    )["data"]["clusters.yaml"]
    runtime_target = next(
        item
        for item in yaml.safe_load(runtime)["clusters"]
        if item["cluster_id"] == "flightpath"
    )
    assert runtime_target["enabled"] is False


def test_flightpath_has_a_distinct_remote_execution_identity() -> None:
    items = [
        item
        for item in yaml.safe_load_all(
            (
                ROOT / "deploy/multicluster/flightpath-remote-rbac.yaml"
            ).read_text()
        )
        if item
    ]
    service_account = resource(
        items, "ServiceAccount", "launchpad-provisioner-flightpath"
    )
    binding = resource(
        items,
        "ClusterRoleBinding",
        "launchpad-provisioner-flightpath-bootstrap",
    )
    argocd_account = resource(
        items, "ServiceAccount", "launchpad-argocd-manager-flightpath"
    )
    argocd_binding = resource(
        items,
        "ClusterRoleBinding",
        "launchpad-argocd-manager-flightpath-discovery",
    )

    assert service_account["metadata"]["namespace"] == "partner-ai-launchpad"
    assert binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "launchpad-provisioner-flightpath",
            "namespace": "partner-ai-launchpad",
        }
    ]
    assert binding["roleRef"]["name"] == (
        "launchpad-flightpath-provisioner-bootstrap"
    )
    assert argocd_account["automountServiceAccountToken"] is False
    assert argocd_binding["subjects"][0]["name"] == (
        "launchpad-argocd-manager-flightpath"
    )
    assert argocd_binding["roleRef"]["name"] == (
        "launchpad-flightpath-argocd-discovery"
    )
    globally_bound_roles = {
        item["roleRef"]["name"]
        for item in items
        if item["kind"] == "ClusterRoleBinding"
    }
    assert "launchpad-flightpath-seat-manager" not in globally_bound_roles
    assert "launchpad-flightpath-argocd-seat-manager" not in globally_bound_roles
    discovery_roles = [
        item
        for item in items
        if item["kind"] == "ClusterRole"
        and item["metadata"]["name"].endswith(("bootstrap", "discovery"))
    ]
    for role in discovery_roles:
        for rule in role["rules"]:
            assert "*" not in rule.get("apiGroups", [])
            assert "*" not in rule.get("resources", [])
            assert "secrets" not in rule.get("resources", [])
    resource(
        items,
        "ValidatingAdmissionPolicy",
        "launchpad-flightpath-namespace-boundary",
    )
    text = (ROOT / "deploy/multicluster/flightpath-remote-rbac.yaml").read_text()
    assert "kind: Secret" not in text
    assert "cluster-admin" not in text.lower()


def test_flightpath_preflight_is_read_only_and_fail_closed() -> None:
    script = (ROOT / "scripts/flightpath-dr-preflight.sh").read_text()

    assert "KUBECONFIG=\"$arena_kubeconfig\" oc" in script
    assert "KUBECONFIG=\"$flightpath_kubeconfig\" oc" in script
    assert "launchpad-arena-kubeconfig" in script
    assert "launchpad-brutus-kubeconfig" in script
    assert "@sha256:" in script
    assert "image-registry.openshift-image-registry.svc" in script
    assert "LAUNCHPAD_CONTROL_PLANE_ROLE" in script
    for mutation in (" oc apply", " oc delete", " oc scale", " oc patch"):
        assert mutation not in script


def test_dr_backup_tool_encrypts_and_requires_explicit_restore_confirmation() -> None:
    script = (ROOT / "scripts/launchpad-dr-database.sh").read_text()

    assert "pg_dump" in script
    assert "pg_restore" in script
    assert "age --encrypt" in script
    assert "age --decrypt" in script
    assert "shasum -a 256" in script
    assert "--confirm-target=flightpath" in script
    assert "https://api.flightpath.fm2aihpcsed.com:6443" in script
    assert "infrastructureName" in script
    assert "Database system identifier" in script
    assert "KUBECONFIG=\"$cluster_kubeconfig\" oc" in script
    assert "mktemp -d" in script
    assert "trap cleanup EXIT" in script
