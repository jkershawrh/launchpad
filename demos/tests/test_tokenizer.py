#!/usr/bin/env python3
"""
Tests for Tokenization & Cost Explorer — /v1/tokenize endpoint

TDD Red Phase: these tests should FAIL until the endpoint is implemented.
"""

import sys
import pytest
from pathlib import Path


MODELS = ["granite-4-0-h-tiny", "codellama-7b-instruct", "llama-scout-17b"]

COST_RATES = {
    "granite-4-0-h-tiny": 0.0004,
    "codellama-7b-instruct": 0.0004,
    "llama-scout-17b": 0.001,
}


@pytest.fixture
def gateway_dir(project_root) -> Path:
    return project_root / "gateway"


@pytest.fixture
def test_client(gateway_dir):
    sys.path.insert(0, str(gateway_dir))
    try:
        from fastapi.testclient import TestClient
        from router import app
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    except ImportError:
        pytest.skip("FastAPI or gateway dependencies not installed")
    finally:
        if str(gateway_dir) in sys.path:
            sys.path.remove(str(gateway_dir))


class TestTokenizeEndpointExists:

    def test_tokenize_endpoint_returns_200(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_tokenize_endpoint_rejects_get(self, test_client):
        resp = test_client.get("/v1/tokenize")
        assert resp.status_code in (404, 405)


class TestTokenizeResponseShape:

    def test_response_has_models_key(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world"})
        data = resp.json()
        assert "models" in data, f"Response missing 'models' key: {data}"

    def test_response_has_all_three_models(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world"})
        data = resp.json()
        for model in MODELS:
            assert model in data["models"], f"Missing model '{model}' in response"

    def test_each_model_has_token_count(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world"})
        data = resp.json()
        for model in MODELS:
            entry = data["models"][model]
            assert "token_count" in entry, f"Model '{model}' missing token_count"
            assert isinstance(entry["token_count"], int)
            assert entry["token_count"] > 0

    def test_each_model_has_tokens_list(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world"})
        data = resp.json()
        for model in MODELS:
            entry = data["models"][model]
            assert "tokens" in entry, f"Model '{model}' missing tokens list"
            assert isinstance(entry["tokens"], list)
            assert len(entry["tokens"]) > 0

    def test_each_model_has_mode(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world"})
        data = resp.json()
        for model in MODELS:
            entry = data["models"][model]
            assert "mode" in entry
            assert entry["mode"] in ("approximate", "real")


class TestTokenizeApproximateMode:

    def test_approximate_mode_is_default(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world"})
        data = resp.json()
        for model in MODELS:
            assert data["models"][model]["mode"] == "approximate"

    def test_approximate_mode_explicit(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world", "mode": "approximate"})
        assert resp.status_code == 200
        data = resp.json()
        for model in MODELS:
            assert data["models"][model]["mode"] == "approximate"

    def test_approximate_token_count_scales_with_text(self, test_client):
        short = test_client.post("/v1/tokenize", json={"text": "Hi"}).json()
        long_text = "This is a much longer sentence with many more words and tokens to count."
        long = test_client.post("/v1/tokenize", json={"text": long_text}).json()
        for model in MODELS:
            assert long["models"][model]["token_count"] > short["models"][model]["token_count"]


class TestTokenizeCost:

    def test_response_has_cost_per_model(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "Hello world"})
        data = resp.json()
        for model in MODELS:
            entry = data["models"][model]
            assert "cost_estimate" in entry, f"Model '{model}' missing cost_estimate"
            assert isinstance(entry["cost_estimate"], (int, float))
            assert entry["cost_estimate"] >= 0

    def test_gaudi_costs_more_than_xeon(self, test_client):
        text = "A reasonably long sentence to generate some tokens for comparison."
        resp = test_client.post("/v1/tokenize", json={"text": text})
        data = resp.json()
        xeon_cost = data["models"]["granite-4-0-h-tiny"]["cost_estimate"]
        gaudi_cost = data["models"]["llama-scout-17b"]["cost_estimate"]
        assert gaudi_cost > xeon_cost, "Gaudi should cost more than Xeon 6"


class TestTokenizeValidation:

    def test_empty_text_rejected(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": ""})
        assert resp.status_code == 422

    def test_missing_text_rejected(self, test_client):
        resp = test_client.post("/v1/tokenize", json={})
        assert resp.status_code == 422

    def test_text_over_max_length_rejected(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "x" * 5001})
        assert resp.status_code == 422

    def test_text_at_max_length_accepted(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "x" * 5000})
        assert resp.status_code == 200

    def test_invalid_mode_rejected(self, test_client):
        resp = test_client.post("/v1/tokenize", json={"text": "hello", "mode": "invalid"})
        assert resp.status_code == 422
