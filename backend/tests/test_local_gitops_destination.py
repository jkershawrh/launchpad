from types import SimpleNamespace

from app.adapters.openshift.provisioning import _gitops_destination_server


def test_local_target_uses_argocd_in_cluster_destination() -> None:
    target = SimpleNamespace(
        local=True,
        api_url="https://api.flightpath.example.test:6443",
    )

    assert _gitops_destination_server(target) == "https://kubernetes.default.svc"


def test_remote_target_preserves_registered_api_destination() -> None:
    target = SimpleNamespace(
        local=False,
        api_url="https://api.arena.example.test:6443",
    )

    assert _gitops_destination_server(target) == ("https://api.arena.example.test:6443")
