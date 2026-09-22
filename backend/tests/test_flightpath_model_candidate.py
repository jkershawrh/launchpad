"""Contracts for the isolated Flightpath-local model-serving candidate."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "deploy/models/flightpath-candidate/granite-3.2-8b-tools.yaml"
SMALL_MANIFEST = ROOT / "deploy/models/flightpath-candidate/granite-2b-cpu.yaml"
KUSTOMIZATION = ROOT / "deploy/models/flightpath-candidate/kustomization.yaml"


def _documents() -> list[dict]:
    return [document for document in yaml.safe_load_all(MANIFEST.read_text()) if document]


def _small_documents() -> list[dict]:
    return [
        document for document in yaml.safe_load_all(SMALL_MANIFEST.read_text()) if document
    ]


def test_candidate_uses_pinned_runtime_and_model_revision():
    documents = _documents()
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    job = next(item for item in documents if item["kind"] == "Job")

    assert deployment["metadata"]["namespace"] == "launchpad-model-candidate"
    assert deployment["metadata"]["annotations"][
        "launchpad.redhat.com/release-eligible"
    ] == "false"
    assert deployment["spec"]["replicas"] == 1

    server = deployment["spec"]["template"]["spec"]["containers"][0]
    downloader = job["spec"]["template"]["spec"]["containers"][0]
    for pod_spec in (
        deployment["spec"]["template"]["spec"],
        job["spec"]["template"]["spec"],
    ):
        assert pod_spec["securityContext"]["hostUsers"] is False
        assert "fsGroup" not in pod_spec["securityContext"]
    expected_image = (
        "registry.redhat.io/rhaii/vllm-cpu-rhel9@sha256:"
        "cf6577f6d526561651df5390aad916c53820a18a1659e3fb39c1c5a62aef0e3c"
    )
    assert server["image"] == expected_image
    assert downloader["image"] == expected_image
    downloader_env = {item["name"]: item["value"] for item in downloader["env"]}
    assert downloader_env["HF_HUB_OFFLINE"] == "0"
    assert downloader_env["TRANSFORMERS_OFFLINE"] == "0"
    assert "610d8c6ee9c84ce51f6dfd7bc5c0215d95d49695" in " ".join(
        downloader["args"]
    )
    assert "--served-model-name=granite-3.2-8b-tools" in server["args"]
    assert "--enable-auto-tool-choice" in server["args"]
    assert "--tool-call-parser=granite" in server["args"]


def test_candidate_cache_is_portable_and_bounded():
    documents = _documents()
    pvc = next(item for item in documents if item["kind"] == "PersistentVolumeClaim")
    deployment = next(item for item in documents if item["kind"] == "Deployment")

    assert pvc["metadata"] == {
        "name": "flightpath-model-cache",
        "namespace": "launchpad-model-candidate",
    }
    assert pvc["spec"]["storageClassName"] == "nfs-storage"
    assert pvc["spec"]["accessModes"] == ["ReadWriteMany"]
    assert pvc["spec"]["resources"]["requests"]["storage"] == "40Gi"

    server = deployment["spec"]["template"]["spec"]["containers"][0]
    assert server["resources"] == {
        "requests": {"cpu": "78", "memory": "64Gi"},
        "limits": {"cpu": "78", "memory": "64Gi"},
    }
    assert deployment["spec"]["strategy"] == {"type": "Recreate"}


def test_candidate_is_private_and_registers_only_the_certified_models():
    documents = _documents()
    service = next(item for item in documents if item["kind"] == "Service")
    policy = next(item for item in documents if item["kind"] == "NetworkPolicy")

    assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
    assert not any(item["kind"] == "Route" for item in documents)
    selectors = policy["spec"]["ingress"]
    assert selectors == [
        {
            "from": [
                {
                    "namespaceSelector": {
                        "matchLabels": {
                            "kubernetes.io/metadata.name": "launchpad-flightpath-candidate"
                        }
                    }
                },
                {
                    "namespaceSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/managed-by": "launchpad"
                        }
                    }
                },
            ],
            "ports": [{"protocol": "TCP", "port": 8080}],
        }
    ]

    registry = yaml.safe_load(
        (
            ROOT
            / "deploy/launchpad/overlays/flightpath-candidate/candidate-clusters.yaml"
        ).read_text()
    )
    target = yaml.safe_load(registry["data"]["clusters.yaml"])["clusters"][0]
    assert "model_endpoint" in target["capabilities"]
    assert target["model_endpoints"] == {
        "granite-2b-cpu": (
            "http://vllm-granite-2b-cpu."
            "launchpad-model-candidate.svc:8080/v1"
        ),
        "granite-3.2-8b-tools": (
            "http://vllm-granite-3-2-8b-tools."
            "launchpad-model-candidate.svc:8080/v1"
        )
    }


def test_candidate_kustomization_contains_only_candidate_resources():
    kustomization = yaml.safe_load(KUSTOMIZATION.read_text())
    assert kustomization["resources"] == [
        "granite-3.2-8b-tools.yaml",
        "granite-2b-cpu.yaml",
    ]


def test_small_candidate_uses_the_pinned_granite_2b_revision():
    documents = _small_documents()
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    job = next(item for item in documents if item["kind"] == "Job")
    service = next(item for item in documents if item["kind"] == "Service")

    assert deployment["metadata"] == {
        "name": "vllm-granite-2b-cpu",
        "namespace": "launchpad-model-candidate",
        "annotations": {"launchpad.redhat.com/release-eligible": "false"},
    }
    server = deployment["spec"]["template"]["spec"]["containers"][0]
    downloader = job["spec"]["template"]["spec"]["containers"][0]
    assert "de37a2ed8ca9d5998813abd8e379b6a5d1aee87c" in " ".join(
        downloader["args"]
    )
    assert "--served-model-name=granite-2b-cpu" in server["args"]
    assert server["resources"] == {
        "requests": {"cpu": "32", "memory": "24Gi"},
        "limits": {"cpu": "32", "memory": "24Gi"},
    }
    assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
    assert not any(item["kind"] == "Route" for item in documents)
