from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy" / "launchpad" / "overlays" / "flightpath-candidate"

EXPECTED = {
    "sales-ai-strategy": "ghcr.io/jkershawrh/red-hat-intel-ai-strategy-web@sha256:09c2f7a226938ff6e085a2b92d6ad88048be95d06a1ad2f9b3c1b15fd1c48732",
    "sales-intel-xeon": "ghcr.io/jkershawrh/intel-xeon-ai-sales-web@sha256:86ac164c2fdb0b6d13f64f897c2b47dfb7b13a5f4821cc3d847d481fd6233ba5",
    "sales-governed-agentic": "ghcr.io/jkershawrh/governed-agentic-ai-sales-web@sha256:4eb250e4e7c87fb7280dc9a3bcf59b94cb93542f8d826ab15672d392a8641ebb",
    "sales-sovereign-ai": "ghcr.io/jkershawrh/sovereign-ai-sales-web@sha256:f1c3d7fc716d3650c6cc1fad2f046e907834c4683369708addf36c8a92fd54a6",
    "sales-virtualization-ai": "ghcr.io/jkershawrh/virtualization-ai-sales-web@sha256:1a976ffcaa557ed8b4f2c3ee5f7c2c0b8a6d6a495c88c8ecf0a54e85f4d550c2",
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

    sales_deployments = [
        item for item in objects
        if item["kind"] == "Deployment" and item["metadata"]["name"] in EXPECTED
    ]
    serialized = yaml.safe_dump_all(sales_deployments)
    assert "qualifier" not in serialized
    assert "proof-api" not in serialized
