from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy" / "launchpad" / "overlays" / "flightpath-candidate"
BOOTSTRAP_OVERLAY = ROOT / "deploy" / "launchpad" / "overlays" / "flightpath-candidate-bootstrap"


def _render() -> list[dict]:
    result = subprocess.run(
        ["oc", "kustomize", str(OVERLAY)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def _render_bootstrap() -> list[dict]:
    result = subprocess.run(
        ["oc", "kustomize", str(BOOTSTRAP_OVERLAY)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def _one(documents: list[dict], kind: str, name: str) -> dict:
    matches = [
        document
        for document in documents
        if document.get("kind") == kind and document.get("metadata", {}).get("name") == name
    ]
    assert len(matches) == 1, (kind, name, len(matches))
    return matches[0]


def test_candidate_is_isolated_and_fail_closed() -> None:
    documents = _render()

    namespace = _one(documents, "Namespace", "launchpad-flightpath-candidate")
    assert namespace["metadata"]["name"] == "launchpad-flightpath-candidate"

    config = _one(documents, "ConfigMap", "launchpad-config")["data"]
    assert config["LAUNCHPAD_CONTROL_CLUSTER_REF"] == "flightpath"
    assert config["LAUNCHPAD_CONTROL_PLANE_ID"] == "flightpath-candidate"
    assert config["LAUNCHPAD_CONTROL_PLANE_ROLE"] == "active"
    assert config["CATALOG_DIR"] == "/opt/catalog"
    assert config["SANDBOX_STORAGE_CLASS"] == "ocs-storagecluster-ceph-rbd"
    assert config["DEMO_FRONTEND_IMAGE"].startswith(
        "quay.io/redhat-gpte/intel-inference-frontend@sha256:"
    )
    assert config["DEMO_GATEWAY_IMAGE"].startswith(
        "quay.io/redhat-gpte/intel-inference-gateway@sha256:"
    )
    assert config["PUBLIC_ACCESS_ENABLED"] == "false"
    assert config["ORPHAN_CLEANUP_ENABLED"] == "false"
    assert config["SMART_PLACEMENT_ENABLED"] == "false"
    assert config["SERIALIZE_WORKSHOP_PROVISIONING"] == "true"
    assert config["KAFKA_BOOTSTRAP_SERVERS"] == ""
    assert "OPENSHIFT_ROUTE_TLS_VERIFY" not in config
    assert config["REMOTE_CONTROL_PLANE_SERVICE_ACCOUNT_NAMESPACE"] == ("openshift-gitops")
    assert config["REMOTE_ARGOCD_SERVICE_ACCOUNT"] == (
        "openshift-gitops-argocd-application-controller"
    )
    assert config["MODEL_CA_BUNDLE_NAMESPACE"] == "launchpad-flightpath-candidate"
    assert set(config["TRUSTED_OAUTH_HOSTS"].split(",")) == {
        "launchpad-candidate.apps.flightpath.fm2aihpcsed.com",
        "launchpad-admin-candidate.apps.flightpath.fm2aihpcsed.com",
        "launchpad-api-candidate.apps.flightpath.fm2aihpcsed.com",
    }

    targets = yaml.safe_load(
        _one(documents, "ConfigMap", "launchpad-cluster-targets")["data"]["clusters.yaml"]
    )["clusters"]
    assert [target["cluster_id"] for target in targets] == ["flightpath"]
    assert targets[0]["local"] is True
    assert targets[0]["enabled"] is True
    assert targets[0]["public_access_enabled"] is False
    assert "credential_secret" not in targets[0]
    assert targets[0]["image_references"] == {
        "showroom_git_cloner": (
            "quay.io/rh-ee-jkershaw/launchpad-showroom-git-cloner@sha256:"
            "2dbcdc5955c5ece1b3bc88c26f85f18122eb317624e1cda160f9d347754d2cc5"
        ),
        "showroom_terminal": (
            "quay.io/rh-ee-jkershaw/launchpad-showroom-terminal@sha256:"
            "324dc5c4201f0da030a572dab389bc8cfdc2f66e800dff3fcee824b7e795daae"
        ),
    }
    assert targets[0]["model_endpoints"] == {
        "granite-2b-cpu": (
            "http://launchpad-candidate-maas.launchpad-flightpath-candidate.svc:4000/v1"
        ),
        "granite-3.2-8b-tools": (
            "http://launchpad-candidate-maas.launchpad-flightpath-candidate.svc:4000/v1"
        ),
    }

    route_hosts = {
        document["metadata"]["name"]: document["spec"]["host"]
        for document in documents
        if document.get("kind") == "Route"
    }
    assert route_hosts == {
        "launchpad": "launchpad-candidate.apps.flightpath.fm2aihpcsed.com",
        "launchpad-admin": "launchpad-admin-candidate.apps.flightpath.fm2aihpcsed.com",
        "launchpad-api": "launchpad-api-candidate.apps.flightpath.fm2aihpcsed.com",
    }

    deployments = {
        document["metadata"]["name"]: document["spec"]["replicas"]
        for document in documents
        if document.get("kind") == "Deployment"
    }
    assert deployments == {
        "admin": 1,
        "backend": 1,
        "lifecycle-worker": 1,
        "launchpad-candidate-maas": 1,
        "partner-portal": 1,
        "postgres": 1,
        "public-access-gateway": 0,
    }
    assert _one(documents, "CronJob", "lifecycle-scheduler")["spec"]["suspend"] is True

    assert not [document for document in documents if document.get("kind") == "Secret"]
    assert not [
        document
        for document in documents
        if document.get("kind") == "ClusterRole"
        and document["metadata"]["name"] == "launchpad-provisioner"
    ]
    candidate_binding = _one(
        documents, "ClusterRoleBinding", "launchpad-flightpath-candidate-provisioner"
    )
    assert candidate_binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "launchpad-backend",
            "namespace": "launchpad-flightpath-candidate",
        }
    ]
    candidate_role = _one(documents, "ClusterRole", "launchpad-flightpath-candidate-provisioner")
    assert any(
        set(rule["apiGroups"]) == {"", "image.openshift.io"}
        and rule["resources"] == ["imagestreams/layers"]
        and rule["verbs"] == ["get"]
        for rule in candidate_role["rules"]
    )
    assert any(
        rule["apiGroups"] == [""]
        and rule["resources"] == ["pods/log"]
        and rule["verbs"] == ["get"]
        for rule in candidate_role["rules"]
    )
    assert any(
        rule["resources"] == ["clusterroles"]
        and "launchpad-flightpath-argocd-seat-manager" in rule["resourceNames"]
        and rule["verbs"] == ["bind"]
        for rule in candidate_role["rules"]
    )
    _one(documents, "ClusterRole", "launchpad-flightpath-argocd-seat-manager")

    for deployment_name, container_name in (
        ("backend", "backend"),
        ("lifecycle-worker", "lifecycle-worker"),
    ):
        deployment = _one(documents, "Deployment", deployment_name)
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(item for item in pod_spec["containers"] if item["name"] == container_name)
        env = {item["name"]: item.get("value") for item in container.get("env", [])}
        mounts = {item["name"]: item for item in container.get("volumeMounts", [])}
        volumes = {item["name"]: item for item in pod_spec.get("volumes", [])}
        assert env["SSL_CERT_FILE"] == "/etc/launchpad-ca/ca-bundle.crt"
        assert env["REQUESTS_CA_BUNDLE"] == "/etc/launchpad-ca/ca-bundle.crt"
        assert mounts["cluster-ca-bundle"]["mountPath"] == "/etc/launchpad-ca"
        assert volumes["cluster-ca-bundle"]["configMap"] == {
            "name": "launchpad-cluster-ca-bundle",
            "optional": False,
        }


def test_candidate_uses_immutable_images() -> None:
    documents = _render()
    workload_kinds = {"Deployment", "CronJob", "Job"}
    images: list[str] = []
    for document in documents:
        if document.get("kind") not in workload_kinds:
            continue
        if document["kind"] in {"Deployment", "Job"}:
            pod_spec = document["spec"]["template"]["spec"]
        else:
            pod_spec = document["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        images.extend(container["image"] for container in pod_spec.get("containers", []))
    assert images
    assert all("@sha256:" in image for image in images)


def test_candidate_has_an_explicit_database_migration_gate() -> None:
    documents = _render()
    migration = next(
        document
        for document in documents
        if document.get("kind") == "Job"
        and document.get("metadata", {})
        .get("name", "")
        .startswith("database-migrate-flightpath-candidate-")
    )
    pod_spec = migration["spec"]["template"]["spec"]
    migration_labels = migration["spec"]["template"]["metadata"]["labels"]
    postgres_allowed_labels = _one(documents, "NetworkPolicy", "postgres-ingress")["spec"][
        "ingress"
    ][0]["from"][0]["podSelector"]["matchLabels"]
    assert migration_labels.items() >= postgres_allowed_labels.items()
    assert pod_spec["restartPolicy"] == "OnFailure"
    assert pod_spec["serviceAccountName"] == "launchpad-backend"
    assert pod_spec["imagePullSecrets"] == [{"name": "launchpad-registry-pull"}]
    container = pod_spec["containers"][0]
    assert "@sha256:" in container["image"]
    assert container["env"][0]["valueFrom"]["secretKeyRef"] == {
        "name": "launchpad-db-secret",
        "key": "DATABASE_URL",
    }


def test_candidate_pins_the_certified_flightpath_showroom_content() -> None:
    documents = _render()
    catalog = yaml.safe_load(
        _one(documents, "ConfigMap", "flightpath-candidate-serve-llms-catalog")["data"][
            "catalog-item.yaml"
        ]
    )
    assert catalog["metadata"]["showroom_content_repo_url"] == (
        "https://github.com/jkershawrh/launchpad.git"
    )
    assert catalog["metadata"]["showroom_content_ref"] == (
        "9526ede61b5c31949f3a1bedd133b5a17e554178"
    )

    for deployment_name, container_name in (
        ("backend", "backend"),
        ("lifecycle-worker", "lifecycle-worker"),
    ):
        deployment = _one(documents, "Deployment", deployment_name)
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(item for item in pod_spec["containers"] if item["name"] == container_name)
        mount = next(
            item for item in container["volumeMounts"] if item["name"] == "candidate-serve-llms-catalog"
        )
        assert mount == {
            "name": "candidate-serve-llms-catalog",
            "mountPath": "/opt/catalog/intel-llm-cpu-serving/catalog-item.yaml",
            "subPath": "catalog-item.yaml",
            "readOnly": True,
        }


def test_candidate_isolates_agent_201_on_flightpath() -> None:
    documents = _render()
    catalog = yaml.safe_load(
        _one(documents, "ConfigMap", "flightpath-candidate-agent-201-catalog")["data"][
            "catalog-item.yaml"
        ]
    )
    metadata = catalog["metadata"]
    assert catalog["catalog_item_id"] == "intel-xeon6-agent-201"
    assert metadata["workshop_cluster_ref"] == "flightpath"
    assert metadata["certification_stage"] == "one-seat-candidate"
    assert metadata["showroom_content_repo_url"] == (
        "https://github.com/jkershawrh/launchpad.git"
    )
    assert metadata["showroom_content_ref"] == (
        "9526ede61b5c31949f3a1bedd133b5a17e554178"
    )
    assert metadata["inference_endpoint"] == "direct_vllm_candidate"

    for deployment_name, container_name in (
        ("backend", "backend"),
        ("lifecycle-worker", "lifecycle-worker"),
    ):
        deployment = _one(documents, "Deployment", deployment_name)
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(item for item in pod_spec["containers"] if item["name"] == container_name)
        assert {
            "name": "candidate-agent-201-catalog",
            "mountPath": "/opt/catalog/intel-xeon6-agent-201/catalog-item.yaml",
            "subPath": "catalog-item.yaml",
            "readOnly": True,
        } in container["volumeMounts"]


def test_candidate_isolates_multi_agent_on_flightpath() -> None:
    documents = _render()
    catalog = yaml.safe_load(
        _one(documents, "ConfigMap", "flightpath-candidate-multi-agent-catalog")["data"][
            "catalog-item.yaml"
        ]
    )
    metadata = catalog["metadata"]
    assert catalog["catalog_item_id"] == "multi-agent-quickstart"
    assert metadata["workshop_cluster_ref"] == "flightpath"
    assert metadata["certification_stage"] == "one-seat-candidate"
    assert metadata["showroom_content_repo_url"] == (
        "https://github.com/jkershawrh/launchpad.git"
    )
    assert metadata["showroom_content_ref"] == (
        "2302acddb0e696ff72b647677049b7de529060e3"
    )
    assert metadata["workload_repo"] == "https://github.com/jkershawrh/launchpad.git"
    assert metadata["workload_revision"] == (
        "2302acddb0e696ff72b647677049b7de529060e3"
    )
    assert metadata["inference_endpoint"] == "direct_vllm_candidate"

    for deployment_name, container_name in (
        ("backend", "backend"),
        ("lifecycle-worker", "lifecycle-worker"),
    ):
        deployment = _one(documents, "Deployment", deployment_name)
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(item for item in pod_spec["containers"] if item["name"] == container_name)
        assert {
            "name": "candidate-multi-agent-catalog",
            "mountPath": "/opt/catalog/multi-agent-quickstart/catalog-item.yaml",
            "subPath": "catalog-item.yaml",
            "readOnly": True,
        } in container["volumeMounts"]


def test_candidate_isolates_hybrid_fraud_on_flightpath() -> None:
    documents = _render()
    catalog = yaml.safe_load(
        _one(documents, "ConfigMap", "flightpath-candidate-hybrid-fraud-catalog")["data"][
            "catalog-item.yaml"
        ]
    )
    metadata = catalog["metadata"]
    assert catalog["status"] == "active"
    assert metadata["workshop_cluster_ref"] == "flightpath"
    assert metadata["certification_stage"] == "twenty-five-seat-candidate"
    assert metadata["max_workshop_seats"] == 25
    assert metadata["inference_endpoint"] == "litellm_virtual_key_candidate"
    assert metadata["seat_cpu_millicores"] == 700
    assert metadata["seat_memory_mib"] == 1280
    assert metadata["seat_pods"] == 2
    assert metadata["namespace_slug"] == "fraud"
    assert metadata["workload_release_name"] == "fraud"
    assert metadata["workload_routes"] == {"ui": "fraud-ui", "scorer": "fraud-scorer"}

    for deployment_name, container_name in (
        ("backend", "backend"),
        ("lifecycle-worker", "lifecycle-worker"),
    ):
        deployment = _one(documents, "Deployment", deployment_name)
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(item for item in pod_spec["containers"] if item["name"] == container_name)
        assert {
            "name": "candidate-hybrid-fraud-catalog",
            "mountPath": "/opt/catalog/hybrid-fraud-detection/catalog-item.yaml",
            "subPath": "catalog-item.yaml",
            "readOnly": True,
        } in container["volumeMounts"]


def test_candidate_maas_enforces_virtual_keys_without_publishing_secrets() -> None:
    documents = _render()

    gateway = _one(documents, "Deployment", "launchpad-candidate-maas")
    assert gateway["spec"]["replicas"] == 1
    pod_spec = gateway["spec"]["template"]["spec"]
    assert gateway["spec"]["template"]["metadata"]["labels"][
        "app.kubernetes.io/managed-by"
    ] == "kustomize"
    container = pod_spec["containers"][0]
    assert container["image"] == (
        "ghcr.io/berriai/litellm@sha256:"
        "9d60771c86a42ced1b918f23dd940a1ac9905ddb02a4fae779cfe1937477c9a0"
    )
    assert container["envFrom"] == [{"secretRef": {"name": "launchpad-litellm"}}]
    assert _one(documents, "Service", "launchpad-candidate-maas")["spec"]["ports"] == [
        {"name": "http", "port": 4000, "targetPort": 4000}
    ]

    config = yaml.safe_load(
        _one(documents, "ConfigMap", "launchpad-candidate-maas-config")["data"][
            "config.yaml"
        ]
    )
    assert config["general_settings"]["master_key"] == "os.environ/LITELLM_API_KEY"
    assert config["general_settings"]["database_url"] == "os.environ/DATABASE_URL"
    assert {item["model_name"] for item in config["model_list"]} == {
        "granite-2b-cpu",
        "granite-3.2-8b-tools",
    }

    targets = yaml.safe_load(
        _one(documents, "ConfigMap", "launchpad-cluster-targets")["data"]["clusters.yaml"]
    )["clusters"]
    assert set(targets[0]["model_endpoints"].values()) == {
        "http://launchpad-candidate-maas.launchpad-flightpath-candidate.svc:4000/v1"
    }

    catalog = yaml.safe_load(
        _one(documents, "ConfigMap", "flightpath-candidate-hybrid-fraud-catalog")["data"][
            "catalog-item.yaml"
        ]
    )
    assert catalog["metadata"]["inference_endpoint"] == "litellm_virtual_key_candidate"

    policy = _one(documents, "NetworkPolicy", "launchpad-candidate-maas-ingress")
    assert policy["spec"]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/name": "launchpad-candidate-maas"
    }
    assert not [document for document in documents if document.get("kind") == "Secret"]


def test_bootstrap_holds_application_workloads_until_migration_is_green() -> None:
    documents = _render_bootstrap()
    for name in (
        "backend",
        "lifecycle-worker",
        "partner-portal",
        "admin",
        "launchpad-candidate-maas",
    ):
        assert _one(documents, "Deployment", name)["spec"]["replicas"] == 0
    assert _one(documents, "Deployment", "postgres")["spec"]["replicas"] == 1

    migration = next(
        document
        for document in documents
        if document.get("kind") == "Job"
        and document.get("metadata", {})
        .get("name", "")
        .startswith("database-migrate-flightpath-candidate-")
    )
    assert migration["spec"]["suspend"] is True
