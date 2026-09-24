from pathlib import Path


CONTAINERFILE = Path(__file__).resolve().parents[1] / "Containerfile"


def test_cluster_clients_are_explicitly_versioned() -> None:
    text = CONTAINERFILE.read_text()

    assert "ARG OPENSHIFT_CLIENT_VERSION=" in text
    assert "ARG HELM_VERSION=" in text
    assert "/ocp/stable/" not in text
    assert "helm-v3.17.3" not in text
    assert "${OPENSHIFT_CLIENT_VERSION}" in text
    assert "${HELM_VERSION}" in text


def test_runtime_removes_unused_node_toolchain_and_updates_packaging_metadata() -> None:
    text = CONTAINERFILE.read_text()

    assert "dnf -y remove npm 'nodejs*'" in text
    assert "pip install --no-cache-dir --upgrade setuptools" in text


def test_downloads_fail_closed() -> None:
    text = CONTAINERFILE.read_text()

    assert text.count("curl --fail --silent --show-error --location") == 2
