"""Contracts for Arena-owned shared model serving used by Launchpad labs."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "deploy/models/arena/granite-3.2-8b-tools.yaml"


def _documents():
    return [doc for doc in yaml.safe_load_all(MANIFEST.read_text()) if doc]


def test_tool_calling_model_is_private_shared_arena_infrastructure():
    documents = _documents()
    deployment = next(doc for doc in documents if doc["kind"] == "Deployment")
    service = next(doc for doc in documents if doc["kind"] == "Service")
    network_policy = next(doc for doc in documents if doc["kind"] == "NetworkPolicy")

    assert deployment["metadata"]["namespace"] == "fleet-llm-d"
    assert deployment["spec"]["replicas"] == 2
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"].startswith("registry.redhat.io/rhaii/vllm-cpu-rhel9@sha256:")
    assert "--enable-auto-tool-choice" in container["args"]
    assert "--tool-call-parser=granite" in container["args"]
    assert "--served-model-name=granite-3.2-8b-tools" in container["args"]
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["startupProbe"]["httpGet"]["path"] == "/health"
    assert {item["name"]: item["value"] for item in container["env"]}[
        "LD_PRELOAD"
    ] == "/usr/lib64/libomp.so"
    # A 48-core reservation passed correctness but regressed the 25-seat
    # Agent 201 journey from ~82s to ~199s. Keep most of the original CPU
    # allocation while recovering 32 cores across the two replicas. Matching
    # request and limit preserves Guaranteed QoS and exclusive CPU placement.
    assert container["resources"]["requests"]["cpu"] == "80"
    assert container["resources"]["limits"]["cpu"] == "80"

    model_volume = next(
        volume
        for volume in deployment["spec"]["template"]["spec"]["volumes"]
        if volume["name"] == "models"
    )
    assert model_volume["persistentVolumeClaim"] == {
        "claimName": "oberon-model-cache",
        "readOnly": True,
    }
    assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
    assert not any(doc["kind"] == "Route" for doc in documents)
    assert network_policy["spec"]["podSelector"]["matchLabels"]["app"] == (
        "vllm-granite-3-2-8b-tools"
    )


def test_arena_registries_and_tool_lab_use_dedicated_endpoint():
    endpoint = (
        "http://vllm-granite-3-2-8b-tools.fleet-llm-d.svc:8080/v1"
    )
    for filename in ("clusters.yaml", "clusters-arena-cert.yaml"):
        config = yaml.safe_load((ROOT / "config" / filename).read_text())
        arena = next(
            cluster for cluster in config["clusters"] if cluster["cluster_id"] == "arena"
        )
        assert arena["model_endpoints"]["granite-3.2-8b-tools"] == endpoint

    catalog = yaml.safe_load(
        (ROOT / "catalog/intel-llm-tool-calling/catalog-item.yaml").read_text()
    )
    assert catalog["metadata"]["required_models"] == ["granite-3.2-8b-tools"]

    overlay = yaml.safe_load(
        (ROOT / "deploy/launchpad/overlays/arena/arena-clusters.yaml").read_text()
    )
    overlay_config = yaml.safe_load(overlay["data"]["clusters.yaml"])
    assert overlay_config["clusters"][0]["model_endpoints"][
        "granite-3.2-8b-tools"
    ] == endpoint
