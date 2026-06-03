"""Tests for TARSy escalation trigger and result handler."""
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("INTEGRATION_API_KEY", "test-integration-key")

from app.integrations.tarsy_escalation import (
    COOLDOWN_SECONDS,
    _cooldown_key,
    _escalation_cooldown,
    check_tarsy_escalation,
    escalate_provision_failure,
)
from app.integrations.tarsy_result_handler import handle_tarsy_result


# ═══════════════════════════════════════════════════════════════════════════════
# check_tarsy_escalation
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckTarsyEscalation:

    def setup_method(self):
        _escalation_cooldown.clear()

    def test_returns_true_when_success_rate_below_threshold_and_enough_attempts(self):
        assert check_tarsy_escalation(
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            success_rate=0.2,
            total_attempts=5,
        ) is True

    def test_returns_true_at_minimum_attempts(self):
        assert check_tarsy_escalation(
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            success_rate=0.0,
            total_attempts=3,
        ) is True

    def test_returns_false_when_success_rate_above_threshold(self):
        assert check_tarsy_escalation(
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            success_rate=0.5,
            total_attempts=10,
        ) is False

    def test_returns_false_when_success_rate_exactly_at_threshold(self):
        assert check_tarsy_escalation(
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            success_rate=0.3,
            total_attempts=10,
        ) is False

    def test_returns_false_when_not_enough_attempts(self):
        assert check_tarsy_escalation(
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            success_rate=0.1,
            total_attempts=2,
        ) is False

    def test_returns_false_during_cooldown(self):
        key = _cooldown_key("demo-a", "cluster-1", "gaudi-endpoint")
        _escalation_cooldown[key] = time.monotonic()

        assert check_tarsy_escalation(
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            success_rate=0.1,
            total_attempts=5,
        ) is False

    def test_returns_true_after_cooldown_expires(self):
        key = _cooldown_key("demo-a", "cluster-1", "gaudi-endpoint")
        _escalation_cooldown[key] = time.monotonic() - COOLDOWN_SECONDS - 1

        assert check_tarsy_escalation(
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            success_rate=0.1,
            total_attempts=5,
        ) is True

    def test_different_tuples_have_independent_cooldowns(self):
        key_a = _cooldown_key("demo-a", "cluster-1", "gaudi-endpoint")
        _escalation_cooldown[key_a] = time.monotonic()

        assert check_tarsy_escalation(
            catalog_item_id="demo-b",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            success_rate=0.1,
            total_attempts=5,
        ) is True


# ═══════════════════════════════════════════════════════════════════════════════
# escalate_provision_failure
# ═══════════════════════════════════════════════════════════════════════════════


class TestEscalateProvisionFailure:

    def setup_method(self):
        _escalation_cooldown.clear()

    @patch("app.integrations.kafka_publisher.publish_tarsy_request")
    def test_builds_correct_payload(self, mock_publish):
        escalate_provision_failure(
            session_id="session-123",
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            error_summary="Timeout waiting for pods",
            feedback_summary={"success_rate": 0.1, "total_attempts": 5},
        )

        mock_publish.assert_called_once()
        request_dict = mock_publish.call_args[0][0]
        assert request_dict["alert_type"] == "ProvisioningFailure"
        assert request_dict["severity"] == "medium"
        assert request_dict["originator_id"] == "session-123"

        data = json.loads(request_dict["data"])
        assert data["catalog_item_id"] == "demo-a"
        assert data["cluster_name"] == "cluster-1"
        assert data["hardware_profile"] == "gaudi-endpoint"
        assert data["error_summary"] == "Timeout waiting for pods"
        assert data["feedback_history"]["success_rate"] == 0.1

        assert request_dict["mcp_override"]["servers"][0]["name"] == "kubernetes-server"
        assert "get_pods" in request_dict["mcp_override"]["servers"][0]["tools"]

    @patch("app.integrations.kafka_publisher.publish_tarsy_request")
    def test_sets_cooldown_after_escalation(self, mock_publish):
        escalate_provision_failure(
            session_id="session-123",
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            error_summary="Timeout",
            feedback_summary={},
        )

        key = _cooldown_key("demo-a", "cluster-1", "gaudi-endpoint")
        assert key in _escalation_cooldown

    @patch("app.integrations.kafka_publisher.publish_tarsy_request", side_effect=Exception("Kafka down"))
    def test_sets_cooldown_even_on_publish_failure(self, mock_publish):
        escalate_provision_failure(
            session_id="session-123",
            catalog_item_id="demo-a",
            cluster_name="cluster-1",
            hardware_profile="gaudi-endpoint",
            error_summary="Timeout",
            feedback_summary={},
        )

        key = _cooldown_key("demo-a", "cluster-1", "gaudi-endpoint")
        assert key in _escalation_cooldown


# ═══════════════════════════════════════════════════════════════════════════════
# handle_tarsy_result
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleTarsyResult:

    @patch("app.integrations.tarsy_result_handler._publish_lifecycle_event")
    def test_processes_ecosystem_event_envelope(self, mock_lifecycle):
        message = {
            "payload": {
                "alert_type": "ProvisioningFailure",
                "originator_id": "session-123",
                "result": {"summary": "Node pressure resolved"},
            }
        }

        handle_tarsy_result(message)
        mock_lifecycle.assert_called_once_with("session-123", message["payload"])

    @patch("app.integrations.tarsy_result_handler._publish_lifecycle_event")
    def test_handles_flat_message(self, mock_lifecycle):
        message = {
            "alert_type": "ProvisioningFailure",
            "originator_id": "session-456",
            "result": {"summary": "GPU driver crash detected"},
        }

        handle_tarsy_result(message)
        mock_lifecycle.assert_called_once()

    @patch("app.integrations.tarsy_result_handler._publish_lifecycle_event", side_effect=Exception("fail"))
    def test_handles_lifecycle_publish_error_silently(self, mock_lifecycle):
        message = {
            "payload": {
                "alert_type": "ProvisioningFailure",
                "originator_id": "session-123",
                "result": {},
            }
        }
        # Should not raise
        handle_tarsy_result(message)
