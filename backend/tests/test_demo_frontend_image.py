import yaml
from app.adapters.openshift.provisioning import (
    DEFAULT_DEMO_FRONTEND_IMAGE,
    DEFAULT_DEMO_GATEWAY_IMAGE,
    OpenShiftProvisioningAdapter,
    _demo_frontend_image,
)


def test_demo_frontend_image_is_cluster_configurable(monkeypatch) -> None:
    pinned = "registry.example.test/demo@sha256:" + "a" * 64
    monkeypatch.setenv("DEMO_FRONTEND_IMAGE", pinned)

    assert _demo_frontend_image() == pinned


def test_execution_images_are_rewritten_for_a_portable_cluster(monkeypatch) -> None:
    frontend = "quay.io/example/frontend@sha256:" + "b" * 64
    gateway = "quay.io/example/gateway@sha256:" + "c" * 64
    monkeypatch.setenv("DEMO_FRONTEND_IMAGE", frontend)
    monkeypatch.setenv("DEMO_GATEWAY_IMAGE", gateway)
    manifest = yaml.safe_dump_all(
        [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "frontend"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {"name": "frontend", "image": DEFAULT_DEMO_FRONTEND_IMAGE}
                            ]
                        }
                    }
                },
            },
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "gateway"},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{"name": "gateway", "image": DEFAULT_DEMO_GATEWAY_IMAGE}]
                        }
                    }
                },
            },
        ],
        sort_keys=False,
    )

    rendered = list(
        yaml.safe_load_all(OpenShiftProvisioningAdapter._inject_execution_images(manifest))
    )

    assert rendered[0]["spec"]["template"]["spec"]["containers"][0]["image"] == frontend
    assert rendered[1]["spec"]["template"]["spec"]["containers"][0]["image"] == gateway
