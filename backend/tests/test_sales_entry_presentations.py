from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy" / "launchpad" / "overlays" / "flightpath-candidate"

EXPECTED = {
    "sales-ai-strategy": "ghcr.io/jkershawrh/red-hat-intel-ai-strategy-web@sha256:158695afa247c8c0df58c94ed7bc82ed40cbb6c9bf138e048cb676f23b961218",
    "sales-intel-xeon": "ghcr.io/jkershawrh/intel-xeon-ai-sales-web@sha256:674e0653dd8fd27bf3f100946abc80dd229add5d7d4faf81e0a6de482fddb5e5",
    "sales-governed-agentic": "ghcr.io/jkershawrh/governed-agentic-ai-sales-web@sha256:266e5d0bfffb68d78d202070c3db94dcb327bc79fb7f2543be87ceaed30d8356",
    "sales-sovereign-ai": "ghcr.io/jkershawrh/sovereign-ai-sales-web@sha256:6fd78a5f584480d4e141b9c9a95638c11311c528fb5465e04c64e8fcf5967f65",
    "sales-virtualization-ai": "ghcr.io/jkershawrh/virtualization-ai-sales-web@sha256:1d5d784cf1683bcc74d3bcdcf44836c1da2faa92c9cbb4fafe19c54ff3aca8d4",
}


def rendered_objects():
    result = subprocess.run(
        ["oc", "kustomize", str(OVERLAY)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [item for item in yaml.safe_load_all(result.stdout) if item]


def test_sales_entries_are_presentation_only_and_digest_pinned():
    objects = rendered_objects()
    deployments = {
        item["metadata"]["name"]: item
        for item in objects
        if item["kind"] == "Deployment" and item["metadata"]["name"] in EXPECTED
    }
    assert set(deployments) == set(EXPECTED)

    for name, expected_image in EXPECTED.items():
        deployment = deployments[name]
        containers = deployment["spec"]["template"]["spec"]["containers"]
        assert [(container["name"], container["image"]) for container in containers] == [
            ("presentation", expected_image)
        ]
        assert deployment["spec"]["template"]["spec"]["automountServiceAccountToken"] is False
        assert deployment["spec"]["template"]["spec"]["imagePullSecrets"] == [
            {"name": "launchpad-registry-pull"}
        ]
        assert containers[0]["resources"]["requests"]["memory"] == "128Mi"
        assert containers[0]["resources"]["limits"]["memory"] == "512Mi"


def test_sales_entries_have_isolated_services_and_tls_routes_but_no_catalog_records():
    objects = rendered_objects()
    for name in EXPECTED:
        service = next(item for item in objects if item["kind"] == "Service" and item["metadata"]["name"] == name)
        route = next(item for item in objects if item["kind"] == "Route" and item["metadata"]["name"] == name)
        assert service["metadata"]["labels"]["launchpad.redhat.com/surface"] == "sales-entry"
        assert route["spec"]["tls"] == {"termination": "edge", "insecureEdgeTerminationPolicy": "Redirect"}
        assert route["spec"]["to"]["name"] == name
        assert route["spec"]["host"] == f"{name}.apps.flightpath.fm2aihpcsed.com"

    sales_deployments = [
        item for item in objects
        if item["kind"] == "Deployment" and item["metadata"]["name"] in EXPECTED
    ]
    serialized = yaml.safe_dump_all(sales_deployments)
    assert "qualifier" not in serialized
    assert "proof-api" not in serialized
