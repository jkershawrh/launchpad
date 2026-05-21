"""Suite 3: StarGate evidence bundle validation."""
import json
from unittest.mock import patch, MagicMock
from app.integrations.stargate_webhook import notify_stargate


class TestEvidenceBundles:

    @patch("app.integrations.stargate_webhook.STARGATE_API_URL", "https://stargate.test")
    @patch("app.integrations.stargate_webhook.urllib.request.urlopen")
    def test_provision_event_payload(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock(status=200)
        notify_stargate(session_id="s1", namespace="ns-1", status="provisioning", lab_code="overdrive", tenant_id="t1")
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["source"] == "launchpad"
        assert payload["session_id"] == "s1"
        assert payload["outcome"] == "info"

    @patch("app.integrations.stargate_webhook.STARGATE_API_URL", "https://stargate.test")
    @patch("app.integrations.stargate_webhook.urllib.request.urlopen")
    def test_ready_event_outcome_pass(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock(status=200)
        notify_stargate(session_id="s2", namespace="ns-2", status="ready", tenant_id="t1")
        payload = json.loads(mock_urlopen.call_args[0][0].data)
        assert payload["outcome"] == "pass"

    @patch("app.integrations.stargate_webhook.STARGATE_API_URL", "https://stargate.test")
    @patch("app.integrations.stargate_webhook.urllib.request.urlopen")
    def test_active_event_outcome_pass(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock(status=200)
        notify_stargate(session_id="s3", namespace="ns-3", status="active", tenant_id="t1")
        payload = json.loads(mock_urlopen.call_args[0][0].data)
        assert payload["outcome"] == "pass"

    @patch("app.integrations.stargate_webhook.STARGATE_API_URL", "https://stargate.test")
    @patch("app.integrations.stargate_webhook.urllib.request.urlopen")
    def test_validation_failed_outcome_fail(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock(status=200)
        notify_stargate(session_id="s4", namespace="ns-4", status="validation_failed", tenant_id="t1")
        payload = json.loads(mock_urlopen.call_args[0][0].data)
        assert payload["outcome"] == "fail"

    @patch("app.integrations.stargate_webhook.STARGATE_API_URL", "https://stargate.test")
    @patch("app.integrations.stargate_webhook.urllib.request.urlopen")
    def test_cleanup_failed_has_error_summary(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock(status=200)
        notify_stargate(session_id="s5", namespace="ns-5", status="cleanup_failed", error_summary="namespace stuck", tenant_id="t1")
        payload = json.loads(mock_urlopen.call_args[0][0].data)
        assert payload["error_summary"] == "namespace stuck"

    @patch("app.integrations.stargate_webhook.STARGATE_API_URL", "https://stargate.test")
    @patch("app.integrations.stargate_webhook.urllib.request.urlopen")
    def test_payload_has_required_fields(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock(status=200)
        notify_stargate(session_id="s6", namespace="ns-6", status="active", lab_code="rag", tenant_id="t1", cluster_name="infra01")
        payload = json.loads(mock_urlopen.call_args[0][0].data)
        for field in ["source", "session_id", "lab_code", "cluster_name", "outcome"]:
            assert field in payload, f"Missing field: {field}"

    @patch("app.integrations.stargate_webhook.STARGATE_API_URL", "")
    def test_empty_url_skips_silently(self):
        notify_stargate(session_id="s7", namespace="ns-7", status="active")

    @patch("app.integrations.stargate_webhook.STARGATE_API_URL", "https://stargate.test")
    @patch("app.integrations.stargate_webhook.urllib.request.urlopen")
    def test_network_error_does_not_crash(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("connection refused")
        notify_stargate(session_id="s8", namespace="ns-8", status="active")
