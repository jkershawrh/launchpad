"""
TDD: AAP (Ansible Automation Platform) integration.
AAPClient calls AAP controller API to launch job templates for provisioning.
"""
import pytest
from unittest.mock import patch, MagicMock



class TestAAPClient:

    def test_aap_client_importable(self):
        """RED: AAPClient should be importable."""
        from app.adapters.aap.client import AAPClient
        client = AAPClient(controller_url="https://dev0.test", token="test-token")
        assert client is not None

    def test_launch_job_template(self):
        """RED: launch_job_template should POST to AAP API."""
        from app.adapters.aap.client import AAPClient
        client = AAPClient(controller_url="https://dev0.test", token="test-token")

        def _mock_request(method, url, **kwargs):
            m = MagicMock()
            if "job_templates/" in url and method == "GET":
                m.status_code = 200
                m.json.return_value = {"results": [{"id": 10, "name": "deploy-demo"}]}
            else:
                m.status_code = 201
                m.json.return_value = {"id": 42, "status": "pending"}
            return m

        with patch("app.adapters.aap.client.requests.request", side_effect=_mock_request):
            result = client.launch_job_template(
                template_name="deploy-demo",
                extra_vars={"namespace": "test-ns", "demo_pages": "overdrive"},
            )
            assert result["id"] == 42

    def test_launch_job_template_by_id(self):
        from app.adapters.aap.client import AAPClient
        client = AAPClient(controller_url="https://dev0.test", token="test-token")

        with patch("app.adapters.aap.client.requests.request") as mock_req:
            mock_req.return_value = MagicMock(status_code=201, json=MagicMock(return_value={"id": 99, "status": "pending"}))
            result = client.launch_job_template_by_id(template_id=15, extra_vars={"namespace": "test-ns"})
            assert result["id"] == 99

    def test_get_job_status(self):
        from app.adapters.aap.client import AAPClient
        client = AAPClient(controller_url="https://dev0.test", token="test-token")

        with patch("app.adapters.aap.client.requests.request") as mock_req:
            mock_req.return_value = MagicMock(status_code=200, json=MagicMock(return_value={"id": 42, "status": "successful"}))
            status = client.get_job_status(42)
            assert status["status"] == "successful"

    def test_wait_for_job_completion(self):
        from app.adapters.aap.client import AAPClient
        client = AAPClient(controller_url="https://dev0.test", token="test-token")

        call_count = 0
        def side_effect(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = {"id": 42, "status": "successful" if call_count >= 3 else "running"}
            return m

        with patch("app.adapters.aap.client.requests.request", side_effect=side_effect):
            result = client.wait_for_job(42, poll_interval=0)
            assert result["status"] == "successful"

    def test_list_job_templates(self):
        from app.adapters.aap.client import AAPClient
        client = AAPClient(controller_url="https://dev0.test", token="test-token")

        with patch("app.adapters.aap.client.requests.request") as mock_req:
            mock_req.return_value = MagicMock(status_code=200, json=MagicMock(return_value={"results": [{"id": 1, "name": "deploy-demo"}, {"id": 2, "name": "reclaim-demo"}]}))
            templates = client.list_job_templates()
            assert len(templates) == 2

    def test_aap_unreachable_raises(self):
        from app.adapters.aap.client import AAPClient, AAPError
        client = AAPClient(controller_url="https://dev0.test", token="test-token")

        with patch("app.adapters.aap.client.requests.request") as mock_req:
            mock_req.side_effect = Exception("connection refused")
            with pytest.raises(AAPError):
                client.launch_job_template_by_id(1, extra_vars={})

    def test_aap_url_from_env(self):
        """RED: should read URL and token from env vars."""
        from app.adapters.aap.client import AAPClient
        with patch.dict("os.environ", {"AAP_URL": "https://env-aap.test", "AAP_TOKEN": "env-token"}):
            client = AAPClient()
            assert client.controller_url == "https://env-aap.test"
