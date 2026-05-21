"""
TDD: SA tokens must use kubeconfig files, not --token CLI args.
Verifies the RHDP provisioner doesn't expose tokens in process arguments.
"""
from unittest.mock import patch, MagicMock

from app.adapters.rhdp.provisioning import RHDPProvisioningAdapter


class TestKubeconfigSecurity:

    def test_kustomize_uses_kubeconfig_not_token_arg(self):
        """RED: _apply_kustomize should use --kubeconfig, not --token."""
        adapter = RHDPProvisioningAdapter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            adapter._apply_kustomize(
                path="demos/deploy/cluster",
                namespace="test-ns",
                api_url="https://api.test:6443",
                token="secret-sa-token-123",
            )
            call_args = mock_run.call_args[0][0]
            assert "--token" not in call_args, \
                f"Token passed as CLI arg (visible in /proc): {call_args}"
            assert "--kubeconfig" in call_args, \
                f"Should use --kubeconfig instead of --token: {call_args}"

    def test_helm_uses_kubeconfig_not_token_arg(self):
        """RED: _deploy_helm should use --kubeconfig, not --kube-token."""
        adapter = RHDPProvisioningAdapter()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            adapter._deploy_helm(
                path="tenant/bootstrap",
                namespace="test-ns",
                api_url="https://api.test:6443",
                token="secret-sa-token-456",
            )
            call_args = mock_run.call_args[0][0]
            assert "--kube-token" not in call_args, \
                f"Token passed as CLI arg (visible in /proc): {call_args}"
            assert "--kubeconfig" in call_args, \
                f"Should use --kubeconfig instead of --kube-token: {call_args}"

    def test_kubeconfig_file_is_cleaned_up(self):
        """RED: temp kubeconfig file should be deleted after use."""
        import os
        adapter = RHDPProvisioningAdapter()
        kubeconfig_paths = []

        def capture_run(cmd, **kwargs):
            for i, arg in enumerate(cmd):
                if arg == "--kubeconfig" and i + 1 < len(cmd):
                    kubeconfig_paths.append(cmd[i + 1])
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = ""
            mock.stderr = ""
            return mock

        with patch("subprocess.run", side_effect=capture_run):
            adapter._apply_kustomize(
                path="demos/deploy/cluster",
                namespace="test-ns",
                api_url="https://api.test:6443",
                token="temp-token",
            )

        assert len(kubeconfig_paths) == 1, "Should have created exactly one kubeconfig"
        assert not os.path.exists(kubeconfig_paths[0]), \
            f"Kubeconfig file should be cleaned up after use: {kubeconfig_paths[0]}"
