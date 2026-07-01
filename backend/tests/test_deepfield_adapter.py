"""Tests for the DeepField adapter — API calls, error handling, graceful degradation."""

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("AUTH_ENABLED", "false")

from app.adapters.deepfield.client import DeepFieldAdapter
from app.domain.orchestration import DeepFieldSignal


class TestDeepFieldAdapterInit:

    def test_no_url_returns_empty_signals(self):
        adapter = DeepFieldAdapter(api_url="")
        assert adapter.get_cluster_signals("c1") == []

    def test_no_url_returns_empty_overview(self):
        adapter = DeepFieldAdapter(api_url="")
        assert adapter.get_fleet_overview() == {}


class TestGetClusterSignals:

    def test_valid_response_parsed(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "signals": [
                {"metric_type": "cpu_utilization", "value": 0.75, "threshold": 0.8, "status": "warning"},
                {"metric_type": "gpu_utilization", "value": 0.3, "threshold": 0.9, "status": "normal"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(get=MagicMock(return_value=mock_resp)))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            signals = adapter.get_cluster_signals("cluster-a")

        assert len(signals) == 2
        assert isinstance(signals[0], DeepFieldSignal)
        assert signals[0].metric_type == "cpu_utilization"
        assert signals[0].value == 0.75
        assert signals[1].status == "normal"

    def test_server_500_returns_empty(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test")

        with patch("httpx.Client") as mock_client:
            mock_get = MagicMock()
            mock_get.raise_for_status.side_effect = Exception("500 Internal Server Error")
            mock_instance = MagicMock()
            mock_instance.get.return_value = mock_get
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            signals = adapter.get_cluster_signals("cluster-a")

        assert signals == []

    def test_connection_timeout_returns_empty(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test")

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.side_effect = TimeoutError("Connection timed out")
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            signals = adapter.get_cluster_signals("cluster-a")

        assert signals == []

    def test_malformed_json_returns_empty(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"unexpected_key": "no signals here"}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(get=MagicMock(return_value=mock_resp)))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            signals = adapter.get_cluster_signals("cluster-a")

        assert signals == []

    def test_empty_signals_list(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"signals": []}

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(get=MagicMock(return_value=mock_resp)))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            signals = adapter.get_cluster_signals("cluster-a")

        assert signals == []


class TestGetFleetOverview:

    def test_valid_multi_cluster_response(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "clusters": {
                "cluster-a": [{"metric_type": "cpu", "value": 0.5, "threshold": 0.8, "status": "normal"}],
                "cluster-b": [{"metric_type": "gpu", "value": 0.9, "threshold": 0.9, "status": "critical"}],
            }
        }

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(get=MagicMock(return_value=mock_resp)))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            overview = adapter.get_fleet_overview()

        assert len(overview) == 2
        assert "cluster-a" in overview
        assert "cluster-b" in overview
        assert isinstance(overview["cluster-b"][0], DeepFieldSignal)

    def test_fleet_overview_error_returns_empty(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test")

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.side_effect = ConnectionError("refused")
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            overview = adapter.get_fleet_overview()

        assert overview == {}


class TestHeaders:

    def test_api_key_included_when_set(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test", api_key="secret-key")
        headers = adapter._headers()
        assert headers["X-API-Key"] == "secret-key"

    def test_no_api_key_when_empty(self):
        adapter = DeepFieldAdapter(api_url="https://deepfield.test", api_key="")
        headers = adapter._headers()
        assert "X-API-Key" not in headers
