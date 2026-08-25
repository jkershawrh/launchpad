from unittest.mock import MagicMock

from app.adapters.openshift.sandbox_provisioning import OpenShiftSandboxProvisioner


def _provisioner():
    provisioner = OpenShiftSandboxProvisioner.__new__(OpenShiftSandboxProvisioner)
    provisioner._core_v1 = MagicMock()
    provisioner._apps_v1 = MagicMock()
    provisioner._rbac_v1 = MagicMock()
    return provisioner


def test_sandbox_cli_identity_is_namespace_scoped():
    provisioner = _provisioner()
    provisioner._create_sandbox_identity("sandbox-one")

    service_account = provisioner._core_v1.create_namespaced_service_account.call_args.kwargs["body"]
    binding = provisioner._rbac_v1.create_namespaced_role_binding.call_args.kwargs["body"]
    assert service_account.metadata.name == "sandbox-user"
    assert binding.role_ref.name == "edit"
    assert binding.subjects[0].kind == "ServiceAccount"
    assert binding.subjects[0].name == "sandbox-user"
    assert binding.subjects[0].namespace == "sandbox-one"


def test_sandbox_pod_uses_cli_identity_and_kubeconfig():
    provisioner = _provisioner()
    provisioner._create_deployment(
        "sandbox-one",
        "minimal",
        {"cpu_request": "100m", "cpu_limit": "1", "memory_request": "256Mi", "memory_limit": "1Gi"},
        ["vscode"],
    )

    deployment = provisioner._apps_v1.create_namespaced_deployment.call_args.args[1]
    pod_spec = deployment.spec.template.spec
    environment = {item.name: item.value for item in pod_spec.containers[0].env}
    assert pod_spec.service_account_name == "sandbox-user"
    assert environment["SANDBOX_NAMESPACE"] == "sandbox-one"
    assert environment["KUBECONFIG"] == "/tmp/launchpad-kubeconfig"
