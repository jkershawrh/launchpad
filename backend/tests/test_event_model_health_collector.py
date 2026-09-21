"""The collector must never manufacture positive model-health evidence."""

import json
import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.services.event_model_health import FileEventModelHealthProvider
from app.services.event_model_health_collector import (
    ModelHealthCollector,
    ModelProbeTarget,
    load_model_probe_targets,
    write_model_health_snapshot,
)

NOW = datetime(2026, 9, 21, 18, 0, tzinfo=UTC)


def _target(**changes):
    values = {
        "cluster_id": "arena",
        "model_id": "granite-8b",
        "readiness_url": "https://ready.example.test/health",
        "route_url": "https://model.example.test/health",
        "inference_url": "https://model.example.test/v1/chat/completions",
        "inference_body": {
            "model": "granite-8b",
            "messages": [{"role": "user", "content": "Reply OK"}],
        },
    }
    values.update(changes)
    return ModelProbeTarget(**values)


def _client(
    *,
    ready=1,
    route_status=200,
    inference_status=200,
    content="OK",
    model="granite-8b",
    ready_cluster="arena",
    ready_model="granite-8b",
):
    def respond(request):
        if request.url.host == "ready.example.test":
            return httpx.Response(
                200,
                json={
                    "cluster_id": ready_cluster,
                    "model_id": ready_model,
                    "ready_replicas": ready,
                },
            )
        if request.url.path == "/health":
            return httpx.Response(route_status)
        return httpx.Response(
            inference_status,
            json={
                "model": model,
                "choices": [{"message": {"content": content}}],
            },
        )

    return httpx.Client(transport=httpx.MockTransport(respond))


def test_positive_evidence_requires_three_real_checks(tmp_path):
    with _client() as client:
        document = ModelHealthCollector(client=client, now=lambda: NOW).collect([_target()])
    assert document["schema_version"] == "1.0"
    assert document["observed_at"] == NOW.isoformat()
    assert document["models"] == [
        {
            "cluster_id": "arena",
            "model_id": "granite-8b",
            "ready_replicas": 1,
            "route_exposed": True,
            "probe_success": True,
        }
    ]
    output = tmp_path / "health.json"
    write_model_health_snapshot(output, document)
    assert FileEventModelHealthProvider(str(output)).load().models[0].probe_success
    assert os.stat(output).st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "override,expected",
    [
        ({"ready": 0}, (0, True, True)),
        ({"ready": "1"}, (0, True, True)),
        ({"route_status": 503}, (1, False, True)),
        ({"inference_status": 503}, (1, True, False)),
        ({"content": ""}, (1, True, False)),
        ({"model": "wrong-model"}, (1, True, False)),
        ({"ready_model": "wrong-model"}, (0, True, True)),
        ({"ready_cluster": "wrong-cluster"}, (0, True, True)),
    ],
)
def test_negative_or_malformed_checks_never_become_healthy(override, expected):
    with _client(**override) as client:
        row = ModelHealthCollector(client=client, now=lambda: NOW).collect([_target()])["models"][0]
    assert (row["ready_replicas"], row["route_exposed"], row["probe_success"]) == expected


def test_network_failure_is_negative_evidence_not_a_collector_crash():
    def fail(_request):
        raise httpx.ConnectError("token=do-not-log")

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        row = ModelHealthCollector(client=client, now=lambda: NOW).collect([_target()])["models"][0]
    assert (row["ready_replicas"], row["route_exposed"], row["probe_success"]) == (0, False, False)
    assert "token" not in json.dumps(row)


def test_missing_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("MISSING_TEST_TOKEN", raising=False)
    with _client() as client, pytest.raises(ValueError, match="credential"):
        ModelHealthCollector(client=client, now=lambda: NOW).collect(
            [_target(inference_token_env="MISSING_TEST_TOKEN")]
        )


def test_timestamp_is_probe_start_and_slow_collection_rejected():
    times = iter([NOW, NOW + timedelta(seconds=121)])
    with _client() as client, pytest.raises(ValueError, match="too long"):
        ModelHealthCollector(client=client, now=lambda: next(times)).collect([_target()])


def test_config_rejects_plaintext_http_and_duplicate_rows():
    with pytest.raises(ValueError):
        _target(inference_url="http://model.example.test/v1/chat/completions")
    with _client() as client, pytest.raises(ValueError, match="duplicate"):
        ModelHealthCollector(client=client, now=lambda: NOW).collect([_target(), _target()])


def test_failed_atomic_replace_keeps_last_good_snapshot(tmp_path, monkeypatch):
    output = tmp_path / "health.json"
    output.write_text("prior")

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        write_model_health_snapshot(
            output, {"schema_version": "1.0", "observed_at": NOW.isoformat(), "models": []}
        )
    assert output.read_text() == "prior"
    assert list(tmp_path.glob(".health.json.*")) == []


def test_trusted_config_rejects_embedded_credentials_and_unknown_fields(tmp_path):
    config = tmp_path / "targets.json"
    payload = _target().model_dump()
    payload["inference_token"] = "plaintext-secret"
    config.write_text(json.dumps({"schema_version": "1.0", "targets": [payload]}))
    with pytest.raises(ValueError):
        load_model_probe_targets(config)
    payload.pop("inference_token")
    config.write_text(json.dumps({"schema_version": "1.0", "targets": [payload]}))
    assert load_model_probe_targets(config) == [_target()]


def test_secret_reference_is_sent_as_header_but_never_written(tmp_path, monkeypatch):
    monkeypatch.setenv("PROBE_TEST_TOKEN", "sensitive-test-value")
    seen = []

    def respond(request):
        seen.append(request.headers.get("authorization"))
        if request.url.host == "ready.example.test":
            return httpx.Response(
                200,
                json={
                    "cluster_id": "arena",
                    "model_id": "granite-8b",
                    "ready_replicas": 1,
                },
            )
        if request.url.path == "/health":
            return httpx.Response(200)
        return httpx.Response(
            200,
            json={
                "model": "granite-8b",
                "choices": [{"message": {"content": "OK"}}],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        document = ModelHealthCollector(client=client, now=lambda: NOW).collect(
            [
                _target(
                    readiness_token_env="PROBE_TEST_TOKEN", inference_token_env="PROBE_TEST_TOKEN"
                )
            ]
        )
    assert seen == ["Bearer sensitive-test-value", None, "Bearer sensitive-test-value"]
    output = tmp_path / "health.json"
    write_model_health_snapshot(output, document)
    assert "sensitive-test-value" not in output.read_text()


def test_explicit_serving_alias_must_match_response_identity():
    with _client(model="granite-serving-revision") as client:
        row = ModelHealthCollector(client=client, now=lambda: NOW).collect(
            [_target(response_model_id="granite-serving-revision")]
        )["models"][0]
    assert row["probe_success"] is True
