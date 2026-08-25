"""TDD tests for PreflightAdapter — Phase 3 gate matrix."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem


def _make_item(required_models=None, **kwargs):
    base = {
        "catalog_item_id": "test-demo",
        "display_name": "Test Demo",
        "category": CatalogCategory.QUICK_START,
        "status": CatalogStatus.ACTIVE,
    }
    if required_models is not None:
        base["metadata"] = {"required_models": required_models}
    base.update(kwargs)
    return CatalogItem(**base)


# ── Gate 3.1: test_passes_when_models_healthy ────────────────────────

class TestPassesWhenModelsHealthy:
    def test_all_models_available(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        item = _make_item(required_models=["granite-2b-cpu", "granite-350m"])

        with patch("app.adapters.openshift.preflight.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [
                    {"id": "granite-2b-cpu"},
                    {"id": "granite-350m"},
                    {"id": "phi3-mini-cpu"},
                ]
            }
            mock_httpx.get.return_value = mock_response

            result = checker.check(item)

        assert result.passed is True
        assert all(c.status == "pass" for c in result.checks)

    def test_sends_bearer_token_when_api_key_is_configured(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000", api_key="test-key")
        item = _make_item(required_models=["granite-2b-cpu"])

        with patch("app.adapters.openshift.preflight.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": [{"id": "granite-2b-cpu"}]}
            mock_httpx.get.return_value = mock_response

            checker.check(item)

        mock_httpx.get.assert_called_once_with(
            "http://fake:4000/models",
            timeout=10,
            headers={"Authorization": "Bearer test-key"},
        )


# ── Gate 3.2: test_fails_when_model_missing ──────────────────────────

class TestFailsWhenModelMissing:
    def test_missing_model_fails(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        item = _make_item(required_models=["granite-2b-cpu", "nonexistent-model"])

        with patch("app.adapters.openshift.preflight.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [{"id": "granite-2b-cpu"}]
            }
            mock_httpx.get.return_value = mock_response

            result = checker.check(item)

        assert result.passed is False
        failed = [c for c in result.checks if c.status == "fail"]
        assert len(failed) == 1
        assert "nonexistent-model" in failed[0].message

    def test_failure_message_names_model(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        item = _make_item(required_models=["missing-model"])

        with patch("app.adapters.openshift.preflight.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": []}
            mock_httpx.get.return_value = mock_response

            result = checker.check(item)

        assert "missing-model" in result.checks[0].message


# ── Gate 3.3: test_fails_when_litellm_unreachable ────────────────────

class TestFailsWhenLiteLLMUnreachable:
    def test_connection_error_fails_gracefully(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        item = _make_item(required_models=["granite-2b-cpu"])

        with patch("app.adapters.openshift.preflight.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("Connection refused")

            result = checker.check(item)

        assert result.passed is False
        assert result.checks[0].status == "fail"
        assert "unreachable" in result.checks[0].message.lower() or "connection" in result.checks[0].message.lower()

    def test_does_not_raise(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        item = _make_item(required_models=["granite-2b-cpu"])

        with patch("app.adapters.openshift.preflight.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("Connection refused")

            result = checker.check(item)
            assert result is not None


# ── Gate 3.4: test_provisioning_rejects_on_failure ───────────────────

class TestProvisioningRejectsOnFailure:
    def test_provision_raises_on_preflight_failure(self):
        from app.adapters.openshift.preflight import PreflightCheck, PreflightResult
        from app.services.provisioning import ProvisioningService

        mock_preflight = MagicMock()
        mock_preflight.check.return_value = PreflightResult(
            passed=False,
            checks=[PreflightCheck(name="model:granite-2b-cpu", status="fail", message="Model not available")],
        )

        mock_catalog = MagicMock()
        mock_catalog.get_item.return_value = _make_item(required_models=["granite-2b-cpu"])

        mock_constraints = MagicMock()
        from app.adapters.interfaces import ConstraintResult
        mock_constraints.evaluate.return_value = ConstraintResult(allowed=True)

        svc = ProvisioningService(
            catalog=mock_catalog,
            constraints=mock_constraints,
            preflight=mock_preflight,
        )

        from app.domain.enums import LabRequestStatus
        from app.domain.models import LabRequest
        request = LabRequest(
            tenant_id="test-tenant",
            requester_id="test-user",
            catalog_item_id="test-demo",
            requested_mode=CatalogCategory.QUICK_START,
        )
        accepted = svc.submit_request(request)

        with pytest.raises(ValueError, match="(?i)preflight"):
            svc.provision(accepted.request_id)


# ── Gate 3.5: test_skipped_when_no_required_models ───────────────────

class TestSkippedWhenNoRequiredModels:
    def test_no_metadata_passes(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        item = _make_item()

        result = checker.check(item)
        assert result.passed is True
        assert len(result.checks) == 0

    def test_empty_required_models_passes(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        item = _make_item(required_models=[])

        result = checker.check(item)
        assert result.passed is True


# ── Gate 3.C1: PreflightAdapter protocol ─────────────────────────────

class TestPreflightProtocol:
    def test_litellm_checker_has_check_method(self):
        from app.adapters.openshift.preflight import LiteLLMPreflightChecker

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        assert hasattr(checker, "check")
        assert callable(checker.check)

    def test_mock_preflight_has_check_method(self):
        from app.adapters.openshift.preflight import MockPreflightAdapter

        adapter = MockPreflightAdapter()
        assert hasattr(adapter, "check")
        assert callable(adapter.check)


# ── Gate 3.C2: PreflightResult model ─────────────────────────────────

class TestPreflightResultModel:
    def test_has_required_fields(self):
        from app.adapters.openshift.preflight import PreflightCheck, PreflightResult

        result = PreflightResult(
            passed=True,
            checks=[PreflightCheck(name="test", status="pass", message="ok")],
        )
        assert result.passed is True
        assert len(result.checks) == 1
        assert result.checks[0].name == "test"
        assert result.checks[0].status == "pass"
        assert result.checks[0].message == "ok"
        assert result.timestamp is not None


# ── Gate 3.T1: Contract test — Mock vs LiteLLM ──────────────────────

class TestContractMockVsLiteLLM:
    def test_both_return_preflight_result(self):
        from app.adapters.openshift.preflight import (
            LiteLLMPreflightChecker,
            MockPreflightAdapter,
            PreflightResult,
        )

        mock = MockPreflightAdapter()
        item = _make_item()

        mock_result = mock.check(item)
        assert isinstance(mock_result, PreflightResult)

        checker = LiteLLMPreflightChecker(api_base="http://fake:4000")
        checker_result = checker.check(item)
        assert isinstance(checker_result, PreflightResult)
        assert type(mock_result) is type(checker_result)
