from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "scripts/render-agent-201-short-routes.py"
SPEC = spec_from_file_location("agent_201_route_adapter", ADAPTER)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _manifest(name: str, port: int, image: str) -> str:
    return yaml.safe_dump_all(
        [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": name},
                "spec": {
                    "selector": {"matchLabels": {"app": name}},
                    "template": {
                        "metadata": {"labels": {"app": name}},
                        "spec": {
                            "containers": [
                                {
                                    "name": name,
                                    "image": image,
                                    "ports": [{"containerPort": port}],
                                }
                            ]
                        },
                    },
                },
            },
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": name},
                "spec": {
                    "selector": {"app": name},
                    "ports": [{"port": port, "targetPort": port}],
                },
            },
            {
                "apiVersion": "route.openshift.io/v1",
                "kind": "Route",
                "metadata": {"name": name},
                "spec": {
                    "to": {"kind": "Service", "name": name},
                    "port": {"targetPort": port},
                },
            },
        ],
        sort_keys=False,
    )


def test_adapter_changes_only_route_name_and_preserves_exact_runtime_contract():
    source = _manifest("solution-agent", 8082, "example/agent@sha256:abc")
    original = list(yaml.safe_load_all(source))
    rendered = list(yaml.safe_load_all(MODULE.adapt_manifest(source, "agent")))

    assert rendered[0] == original[0]
    assert rendered[1] == original[1]
    expected_route = deepcopy(original[2])
    expected_route["metadata"]["name"] = "agent"
    assert rendered[2] == expected_route
    assert rendered[2]["spec"]["to"]["name"] == "solution-agent"
    assert rendered[2]["spec"]["port"]["targetPort"] == 8082


def test_adapter_defines_all_and_only_short_launchpad_aliases():
    assert MODULE.ROUTE_ALIASES == {
        "solution-tools": "tools",
        "solution-agent": "agent",
        "solution-ui": "app",
    }
    assert MODULE.RAW_PREFIX.endswith(
        "c8dcf5bcef1f926aa5867bcc1b86b69ec33b988d/infrastructure/manifests-201/"
    )


def test_adapter_fails_closed_on_unknown_or_mismatched_route():
    unknown = _manifest("unexpected", 8443, "example/unknown@sha256:def")
    try:
        MODULE.adapt_manifest(unknown, "agent")
    except ValueError as exc:
        assert "unsupported Triforce Route" in str(exc)
    else:
        raise AssertionError("unknown Route did not fail closed")

    solution_agent = _manifest("solution-agent", 8082, "example/agent@sha256:abc")
    try:
        MODULE.adapt_manifest(solution_agent, "app")
    except ValueError as exc:
        assert "not 'app'" in str(exc)
    else:
        raise AssertionError("mismatched alias did not fail closed")
