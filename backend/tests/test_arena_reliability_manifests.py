"""Contracts for the Arena control-plane reliability guardrails."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy/launchpad/overlays/arena"


def _documents(name: str) -> list[dict]:
    return [
        document
        for document in yaml.safe_load_all((OVERLAY / name).read_text())
        if document
    ]


def test_arena_overlay_installs_reliability_resources():
    kustomization = yaml.safe_load((OVERLAY / "kustomization.yaml").read_text())
    assert "reliability.yaml" in kustomization["resources"]
    assert "argocd-monitoring-rbac.yaml" in kustomization["resources"]

    documents = _documents("reliability.yaml")
    rules = next(item for item in documents if item["kind"] == "PrometheusRule")
    alert_names = {
        rule["alert"]
        for group in rules["spec"]["groups"]
        for rule in group["rules"]
    }
    assert {
        "ArenaWorkerNotReady",
        "ArenaIngressRouterReplicaUnavailable",
        "LaunchpadControlPlaneUnavailable",
        "LaunchpadReconcilerFailed",
    } <= alert_names
    control_plane_alert = next(
        rule
        for group in rules["spec"]["groups"]
        for rule in group["rules"]
        if rule["alert"] == "LaunchpadControlPlaneUnavailable"
    )
    assert "postgres" in control_plane_alert["expr"]

    pdbs = [item for item in documents if item["kind"] == "PodDisruptionBudget"]
    assert {item["metadata"]["name"] for item in pdbs} == {
        "partner-portal",
        "launchpad-admin",
        "public-access-gateway",
    }
    assert all(item["spec"]["minAvailable"] == 1 for item in pdbs)


def test_argocd_monitoring_access_is_namespace_scoped_and_least_privilege():
    documents = _documents("argocd-monitoring-rbac.yaml")
    role = next(item for item in documents if item["kind"] == "Role")
    binding = next(item for item in documents if item["kind"] == "RoleBinding")

    assert role["metadata"]["namespace"] == "partner-ai-launchpad"
    assert role["rules"] == [
        {
            "apiGroups": ["monitoring.coreos.com"],
            "resources": ["prometheusrules"],
            "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"],
        }
    ]
    assert binding["metadata"]["namespace"] == "partner-ai-launchpad"
    assert binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": "launchpad-argocd-prometheusrules",
    }
    assert binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "openshift-gitops-argocd-application-controller",
            "namespace": "openshift-gitops",
        }
    ]


def test_arena_stateless_frontends_keep_spread_rules_but_do_not_overstate_ha():
    documents = _documents("patch-runtime.yaml")
    deployments = {
        item["metadata"]["name"]: item
        for item in documents
        if item["kind"] == "Deployment"
    }

    for name in ("partner-portal", "admin", "public-access-gateway"):
        deployment = deployments[name]
        # Arena currently has one schedulable worker. The spread contract is
        # ready for the second worker, but asking for two replicas now would
        # leave one Pending and would not provide availability.
        assert deployment["spec"]["replicas"] == 1
        assert deployment["spec"]["strategy"] == {
            "type": "RollingUpdate",
            "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0},
        }
        constraints = deployment["spec"]["template"]["spec"][
            "topologySpreadConstraints"
        ]
        assert constraints == [
            {
                "maxSkew": 1,
                "topologyKey": "kubernetes.io/hostname",
                "whenUnsatisfiable": "DoNotSchedule",
                "labelSelector": {
                    "matchLabels": {"app.kubernetes.io/name": name}
                },
            }
        ]


def test_backend_single_replica_limit_is_explicit():
    documents = _documents("patch-runtime.yaml")
    backend = next(
        item
        for item in documents
        if item["kind"] == "Deployment" and item["metadata"]["name"] == "backend"
    )
    annotations = backend["metadata"]["annotations"]
    assert annotations["launchpad.redhat.com/ha-blocker"] == (
        "in-memory-session-cache-must-be-externalized-before-replicas-exceed-one"
    )
    assert backend["spec"]["strategy"] == {"type": "Recreate"}
    container = next(
        item
        for item in backend["spec"]["template"]["spec"]["containers"]
        if item["name"] == "backend"
    )
    assert container["resources"] == {
        "requests": {"cpu": "250m", "memory": "1Gi"},
        "limits": {"cpu": "1", "memory": "2Gi"},
    }


def test_arena_backend_runs_on_the_stable_execution_worker():
    documents = _documents("patch-runtime.yaml")
    backend = next(
        item
        for item in documents
        if item["kind"] == "Deployment" and item["metadata"]["name"] == "backend"
    )

    assert backend["spec"]["template"]["spec"]["nodeSelector"] == {
        "kubernetes.io/hostname": "gnr2.fm2aihpcsed.com"
    }


def test_arena_postgres_runs_on_the_stable_execution_worker():
    documents = _documents("patch-runtime.yaml")
    postgres = next(
        item
        for item in documents
        if item["kind"] == "Deployment" and item["metadata"]["name"] == "postgres"
    )

    assert postgres["spec"]["template"]["spec"]["nodeSelector"] == {
        "kubernetes.io/hostname": "gnr2.fm2aihpcsed.com"
    }


def test_arena_reconciler_runs_on_the_stable_execution_worker():
    reconciler = next(
        item
        for item in _documents("operations-automation.yaml")
        if item["kind"] == "CronJob"
        and item["metadata"]["name"] == "launchpad-resource-reconciler"
    )

    assert reconciler["spec"]["jobTemplate"]["spec"]["template"]["spec"][
        "nodeSelector"
    ] == {"kubernetes.io/hostname": "gnr2.fm2aihpcsed.com"}


def test_arena_reconciler_is_admitted_by_postgres_network_policy():
    reconciler = next(
        item
        for item in _documents("operations-automation.yaml")
        if item["kind"] == "CronJob"
        and item["metadata"]["name"] == "launchpad-resource-reconciler"
    )

    labels = reconciler["spec"]["jobTemplate"]["spec"]["template"][
        "metadata"
    ]["labels"]
    assert labels["app.kubernetes.io/managed-by"] == "kustomize"
    assert labels["app.kubernetes.io/part-of"] == "partner-ai-launchpad"


def test_cpu_model_readiness_does_not_flap_during_a_participant_burst():
    patch = yaml.safe_load(
        (OVERLAY / "operational-patches/ovms-granite-2b-readiness.yaml").read_text()
    )
    containers = {
        container["name"]: container
        for container in patch["spec"]["template"]["spec"]["containers"]
    }
    for name in ("ovms", "tls-proxy"):
        probe = containers[name]["readinessProbe"]
        assert probe["timeoutSeconds"] == 5
        assert probe["failureThreshold"] == 6

    assert patch["spec"]["template"]["spec"]["nodeSelector"] == {
        "kubernetes.io/hostname": "gnr2.fm2aihpcsed.com"
    }

    driver = (ROOT / "scripts/apply-arena-model-readiness.sh").read_text()
    assert "*config-arena*" in driver
    assert "refusing to mutate a non-Arena cluster" in driver
    assert "ovms-granite-2b-readiness.yaml" in driver


def test_agent_model_has_two_replicas_for_concurrent_participant_use():
    resources = list(
        yaml.safe_load_all(
            (ROOT / "deploy/models/arena/granite-3.2-8b-tools.yaml").read_text()
        )
    )
    deployment = next(resource for resource in resources if resource["kind"] == "Deployment")

    assert deployment["spec"]["replicas"] == 2
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert "--max-num-seqs=64" in container["args"]
    assert container["readinessProbe"]["timeoutSeconds"] == 5
