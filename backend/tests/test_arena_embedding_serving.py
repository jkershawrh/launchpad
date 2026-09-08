from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "deploy/models/arena/nomic-embed-text-v1.5.yaml"
ENDPOINT = "http://tei-nomic-embed.fleet-llm-d.svc:8080/v1"


def _documents():
    return [document for document in yaml.safe_load_all(MANIFEST.read_text()) if document]


def test_arena_embedding_service_is_private_cached_and_pinned():
    documents = _documents()
    resources = {(doc["kind"], doc["metadata"]["name"]): doc for doc in documents}

    pvc = resources[("PersistentVolumeClaim", "tei-nomic-cache")]
    deployment = resources[("Deployment", "tei-nomic-embed")]
    service = resources[("Service", "tei-nomic-embed")]
    policy = resources[("NetworkPolicy", "allow-launchpad-to-nomic-embed")]

    assert all(doc["metadata"]["namespace"] == "fleet-llm-d" for doc in documents)
    assert not any(doc["kind"] == "Route" for doc in documents)
    assert pvc["spec"]["storageClassName"] == "nfs-storage"
    assert pvc["spec"]["accessModes"] == ["ReadWriteMany"]
    assert pvc["spec"]["resources"]["requests"]["storage"] == "10Gi"

    assert deployment["spec"]["replicas"] == 1
    assert deployment["spec"]["strategy"] == {"type": "Recreate"}
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == (
        "ghcr.io/huggingface/text-embeddings-inference"
        "@sha256:c26a226262ad4ff3330fb30b76653c1bb65da2fcf413b92284545a010e0a8a48"
    )
    assert "--model-id=nomic-ai/nomic-embed-text-v1.5" in container["args"]
    assert "--revision=e5cf08aadaa33385f5990def41f7a23405aec398" in container["args"]
    assert "--served-model-name=nomic-embed-text-v1.5" in container["args"]
    assert deployment["spec"]["progressDeadlineSeconds"] == 1200
    assert container["startupProbe"]["httpGet"]["path"] == "/health"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["resources"]["requests"] == {"cpu": "4", "memory": "4Gi"}
    assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
    assert policy["spec"]["podSelector"]["matchLabels"]["app"] == "tei-nomic-embed"
    assert set(policy["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    egress = policy["spec"]["egress"]
    assert any(
        destination.get("ipBlock", {}).get("cidr") == "172.30.0.10/32"
        for rule in egress
        for destination in rule.get("to", [])
    )
    assert any(
        destination.get("ipBlock", {}).get("cidr") == "0.0.0.0/0"
        and {port["port"] for port in rule["ports"]} == {443}
        for rule in egress
        for destination in rule.get("to", [])
    )


def test_arena_embedding_service_is_registered_and_deployable_as_a_model_bundle():
    kustomization = yaml.safe_load((ROOT / "deploy/models/arena/kustomization.yaml").read_text())
    assert {
        "granite-3.2-8b-tools.yaml",
        "nomic-embed-text-v1.5.yaml",
    } <= set(kustomization["resources"])

    for filename in ("clusters.yaml", "clusters-arena-cert.yaml"):
        config = yaml.safe_load((ROOT / "config" / filename).read_text())
        arena = next(cluster for cluster in config["clusters"] if cluster["cluster_id"] == "arena")
        assert arena["model_endpoints"]["nomic-embed-text-v1.5"] == ENDPOINT

    overlay = yaml.safe_load(
        (ROOT / "deploy/launchpad/overlays/arena/arena-clusters.yaml").read_text()
    )
    overlay_config = yaml.safe_load(overlay["data"]["clusters.yaml"])
    assert overlay_config["clusters"][0]["model_endpoints"]["nomic-embed-text-v1.5"] == ENDPOINT
