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
    backend = resource(items, "Deployment", "backend")
    worker = resource(items, "Deployment", "lifecycle-worker")
    scheduler = resource(items, "CronJob", "lifecycle-scheduler")
    legacy = resource(items, "CronJob", "launchpad-resource-reconciler")

    assert config["data"]["LIFECYCLE_HA_ENABLED"] == "true"
    assert backend["spec"]["template"]["metadata"]["annotations"] == {
        "launchpad.redhat.com/lifecycle-ha-config": "arena-ha-pilot-v1"
    }
    assert worker["spec"]["replicas"] == 2
    assert worker["spec"]["strategy"] == {
        "type": "RollingUpdate",
        "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0},
    }
    assert worker["spec"]["template"]["spec"]["topologySpreadConstraints"] == [
        {
            "maxSkew": 1,
            "topologyKey": "kubernetes.io/hostname",
            "whenUnsatisfiable": "DoNotSchedule",
            "labelSelector": {
                "matchLabels": {
                    "app.kubernetes.io/managed-by": "kustomize",
                    "app.kubernetes.io/name": "lifecycle-worker",
                }
            },
        }
    ]
    assert worker["spec"]["template"]["spec"]["affinity"]["podAntiAffinity"] == {
        "requiredDuringSchedulingIgnoredDuringExecution": [
            {
                "labelSelector": {
                    "matchExpressions": [
                        {
                            "key": "app.kubernetes.io/name",
                            "operator": "In",
                            "values": ["lifecycle-worker"],
                        }
                    ]
                },
                "topologyKey": "kubernetes.io/hostname",
            }
        ]
    }
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


def test_arena_singleton_control_plane_can_reschedule_between_workers() -> None:
    items = render("deploy/launchpad/overlays/arena")

    for deployment_name in ("backend", "postgres"):
        deployment = resource(items, "Deployment", deployment_name)
        node_selector = deployment["spec"]["template"]["spec"].get(
            "nodeSelector", {}
        )
        assert "kubernetes.io/hostname" not in node_selector


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
    assert not [item for item in items if item["kind"] == "Secret"]

    overlay_text = "\n".join(
        path.read_text()
        for path in (ROOT / "deploy/launchpad/overlays/flightpath-dr").glob("*")
        if path.is_file()
    ).lower()
    assert "kubeadmin" not in overlay_text
    assert "pass" + "word:" not in overlay_text


def test_flightpath_dr_gitops_install_is_pinned_and_manually_approved() -> None:
    items = render("deploy/launchpad/overlays/flightpath-dr-gitops/operator")
    subscription = resource(
        items, "Subscription", "openshift-gitops-operator"
    )

    assert subscription["metadata"]["namespace"] == (
        "openshift-gitops-operator"
    )
    assert subscription["spec"] == {
        "channel": "gitops-1.21",
        "installPlanApproval": "Manual",
        "name": "openshift-gitops-operator",
        "source": "redhat-operators",
        "sourceNamespace": "openshift-marketplace",
        "startingCSV": "openshift-gitops-operator.v1.21.4",
    }


def test_flightpath_dr_gitops_control_plane_is_narrow_and_passive() -> None:
    items = render(
        "deploy/launchpad/overlays/flightpath-dr-gitops/control-plane"
    )
    argocd = resource(items, "ArgoCD", "openshift-gitops")
    local_reader = resource(
        items, "Role", "launchpad-remote-cluster-config-reader"
    )
    application_manager = resource(
        items, "Role", "launchpad-application-manager"
    )
    application_binding = resource(
        items, "RoleBinding", "launchpad-application-manager"
    )

    assert argocd["metadata"]["namespace"] == "openshift-gitops"
    assert argocd["spec"]["controller"]["resources"]["requests"] == {
        "cpu": "500m",
        "memory": "4Gi",
    }
    assert local_reader["metadata"]["namespace"] == "partner-ai-launchpad"
    secret_rule = next(
        rule for rule in local_reader["rules"]
        if "secrets" in rule.get("resources", [])
    )
    assert secret_rule["resourceNames"] == [
        "launchpad-arena-kubeconfig",
        "launchpad-brutus-kubeconfig",
    ]
    assert secret_rule["verbs"] == ["get"]
    assert application_manager["metadata"]["namespace"] == "openshift-gitops"
    assert application_manager["rules"] == [
        {
            "apiGroups": ["argoproj.io"],
            "resources": ["applications"],
            "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"],
        }
    ]
    assert application_binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "launchpad-backend",
            "namespace": "partner-ai-launchpad",
        }
    ]

    config = resource(
        render("deploy/launchpad/overlays/flightpath-dr"),
        "ConfigMap",
        "launchpad-config",
    )
    assert config["data"]["SHOWROOM_ARGOCD_NAMESPACE"] == "openshift-gitops"


def test_flightpath_dr_uses_digest_pinned_external_first_party_images() -> None:
    items = render("deploy/launchpad/overlays/flightpath-dr")
    expected = {
        "backend": (
            "quay.io/redhat-gpte/launchpad-backend@"
            "sha256:1e097350a1cb07eea5a991fa40d4fe8afe44cc48923f8a223a3eef07adeb8dcb"
        ),
        "partner-portal": (
            "quay.io/redhat-gpte/launchpad-portal@"
            "sha256:f97cd9cd7a3d51eb5709c92131c11ae02e73901b5232ad7731171f286d6b10c3"
        ),
        "admin": (
            "quay.io/redhat-gpte/launchpad-admin@"
            "sha256:d76bf69b7720efced8ed328e0a0ac863d2e6f96b056f67bb3e6507a73a37ee4e"
        ),
    }
    observed: dict[str, set[str]] = {name: set() for name in expected}

    for item in items:
        pod_spec = None
        if item["kind"] == "Deployment":
            pod_spec = item["spec"]["template"]["spec"]
        elif item["kind"] == "CronJob":
            pod_spec = item["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        if pod_spec is None:
            continue
        for container in pod_spec.get("containers", []):
            if container["name"] in observed:
                observed[container["name"]].add(container["image"])

    assert observed == {
        name: {image}
        for name, image in expected.items()
    }


def test_every_flightpath_workload_image_is_digest_pinned() -> None:
    items = render("deploy/launchpad/overlays/flightpath-dr")
    images: list[str] = []

    for item in items:
        pod_spec = None
        if item["kind"] == "Deployment":
            pod_spec = item["spec"]["template"]["spec"]
        elif item["kind"] == "CronJob":
            pod_spec = item["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        if pod_spec is not None:
            images.extend(
                container["image"]
                for container in pod_spec.get("containers", [])
            )

    assert images
    assert all("@sha256:" in image for image in images)
    assert not any(":latest" in image for image in images)


def test_flightpath_dr_private_registry_access_is_explicit_and_out_of_band() -> None:
    items = render("deploy/launchpad/overlays/flightpath-dr")
    workloads = [
        item
        for item in items
        if item["kind"] in {"Deployment", "CronJob"}
    ]

    assert workloads
    for item in workloads:
        if item["kind"] == "Deployment":
            pod_spec = item["spec"]["template"]["spec"]
        else:
            pod_spec = item["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert pod_spec["imagePullSecrets"] == [
            {"name": "launchpad-registry-pull"}
        ]

    assert not any(
        item["kind"] == "Secret"
        and item["metadata"]["name"] == "launchpad-registry-pull"
        for item in items
    )

    preflight = (ROOT / "scripts/flightpath-dr-preflight.sh").read_text()
    assert "launchpad-registry-pull" in preflight


def test_flightpath_control_plane_has_no_local_cluster_provisioner_binding() -> None:
    items = render("deploy/launchpad/overlays/flightpath-dr")

    assert not any(
        item["kind"] in {"ClusterRole", "ClusterRoleBinding"}
        and item["metadata"]["name"].startswith("launchpad-provisioner")
        for item in items
    )


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
    policy = resource(
        items,
        "ValidatingAdmissionPolicy",
        "launchpad-flightpath-namespace-boundary",
    )
    expression = policy["spec"]["validations"][0]["expression"]
    assert "request.namespace == 'partner-ai-launchpad'" not in expression


def test_flightpath_preflight_is_read_only_and_fail_closed() -> None:
    script = (ROOT / "scripts/flightpath-dr-preflight.sh").read_text()

    assert "KUBECONFIG=\"$arena_kubeconfig\" oc" in script
    assert "KUBECONFIG=\"$flightpath_kubeconfig\" oc" in script
    assert "launchpad-arena-kubeconfig" in script
    assert "launchpad-brutus-kubeconfig" in script
    assert "@sha256:" in script
    assert "image-registry.openshift-image-registry.svc" in script
    assert "LAUNCHPAD_CONTROL_PLANE_ROLE" in script
    assert "applications.argoproj.io" in script
    assert "openshift-gitops-application-controller" in script
    assert "launchpad-arena-argocd-cluster" in script
    assert "launchpad-brutus-argocd-cluster" in script
    assert "launchpad-application-manager" in script
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
