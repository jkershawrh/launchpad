from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/maas/arena-granite-candidate.yaml"


def _documents():
    return [doc for doc in yaml.safe_load_all(MANIFEST.read_text()) if doc]


def test_candidate_manifest_is_isolated_and_contains_no_secret_material():
    documents = _documents()
    kinds = [doc["kind"] for doc in documents]

    assert "Secret" not in kinds
    assert kinds == [
        "Namespace",
        "ServiceAccount",
        "ExternalProvider",
        "ExternalModel",
        "MaaSModelRef",
        "DestinationRule",
        "MaaSSubscription",
        "MaaSAuthPolicy",
    ]
    assert all(
        doc.get("metadata", {}).get("labels", {}).get("launchpad.redhat.com/scope")
        == "candidate"
        for doc in documents
    )
    assert all(
        doc.get("metadata", {}).get("labels", {}).get("launchpad.redhat.com/release-eligible")
        == "false"
        for doc in documents
    )


def test_candidate_reuses_granite_service_without_creating_a_model_workload():
    documents = _documents()
    external_provider = next(doc for doc in documents if doc["kind"] == "ExternalProvider")
    external_model = next(doc for doc in documents if doc["kind"] == "ExternalModel")
    model_ref = next(doc for doc in documents if doc["kind"] == "MaaSModelRef")

    assert external_provider["metadata"]["namespace"] == "launchpad-maas-candidates"
    assert "annotations" not in external_provider["metadata"]
    assert external_provider["spec"] == {
        "provider": "openai",
        "endpoint": "vllm-granite-3-2-8b-tools-fleet-llm-d.apps.arena.fm2aihpcsed.com",
        "auth": {
            "type": "apikey",
            "secretRef": {"name": "granite-candidate-upstream-credential"},
        },
    }
    assert external_model["spec"]["modelName"] == "granite-3-2-8b-tools-candidate"
    assert external_model["spec"]["externalProviderRefs"] == [
        {
            "ref": {"name": "granite-3-2-8b-tools-candidate"},
            "targetModel": "granite-3.2-8b-tools",
            "apiFormat": "openai-chat",
            "path": "/v1/chat/completions",
            "weight": 1,
        }
    ]
    assert model_ref["spec"]["modelRef"] == {
        "kind": "ExternalModel",
        "name": "granite-3-2-8b-tools-candidate",
    }
    assert model_ref["spec"]["tenantRef"] == "models-as-a-service"
    assert not any(kind in {"Deployment", "StatefulSet", "LLMInferenceService"} for kind in [doc["kind"] for doc in documents])


def test_candidate_trusts_arena_ingress_ca_without_disabling_verification():
    destination_rule = next(doc for doc in _documents() if doc["kind"] == "DestinationRule")
    tls = destination_rule["spec"]["trafficPolicy"]["tls"]

    assert destination_rule["metadata"]["namespace"] == "openshift-ingress"
    assert destination_rule["spec"]["exportTo"] == ["."]
    assert destination_rule["spec"]["host"] == (
        "vllm-granite-3-2-8b-tools-fleet-llm-d.apps.arena.fm2aihpcsed.com"
    )
    assert tls == {
        "mode": "SIMPLE",
        "sni": "vllm-granite-3-2-8b-tools-fleet-llm-d.apps.arena.fm2aihpcsed.com",
        "credentialName": "granite-candidate-arena-ingress-ca",
    }
    assert "insecureSkipVerify" not in tls


def test_candidate_access_is_one_identity_with_bounded_quota():
    documents = _documents()
    subscription = next(doc for doc in documents if doc["kind"] == "MaaSSubscription")
    policy = next(doc for doc in documents if doc["kind"] == "MaaSAuthPolicy")
    expected_user = "system:serviceaccount:launchpad-maas-candidates:hybrid-fraud-candidate"
    expected_ref = {
        "name": "granite-3-2-8b-tools-candidate",
        "namespace": "launchpad-maas-candidates",
    }

    assert subscription["spec"]["owner"] == {"users": [expected_user]}
    assert policy["spec"]["subjects"] == {"users": [expected_user]}
    assert policy["spec"]["modelRefs"] == [expected_ref]
    model_subscription = subscription["spec"]["modelRefs"][0]
    assert {key: model_subscription[key] for key in ("name", "namespace")} == expected_ref
    assert model_subscription["tokenRateLimits"] == [{"limit": 120000, "window": "1h"}]
