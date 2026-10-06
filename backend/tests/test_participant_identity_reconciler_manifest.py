from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT / "deploy/launchpad/overlays/flightpath-candidate/participant-identity-reconciler.yaml"
)


def _documents() -> list[dict]:
    return [item for item in yaml.safe_load_all(MANIFEST.read_text()) if item]


def test_identity_reconciler_has_a_dedicated_service_account_and_minimal_role() -> None:
    documents = _documents()
    cronjob = next(item for item in documents if item["kind"] == "CronJob")
    role = next(item for item in documents if item["kind"] == "ClusterRole")
    pod = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    pod_labels = cronjob["spec"]["jobTemplate"]["spec"]["template"]["metadata"][
        "labels"
    ]

    assert pod["serviceAccountName"] == "launchpad-participant-identity-reconciler"
    assert pod_labels["app.kubernetes.io/part-of"] == "partner-ai-launchpad"
    assert pod_labels["app.kubernetes.io/managed-by"] == "kustomize"
    assert pod["containers"][0]["command"] == [
        "python",
        "-m",
        "app.identity_reconciler_main",
    ]
    assert role["rules"] == [
        {
            "apiGroups": ["oauth.openshift.io"],
            "resources": ["oauthaccesstokens"],
            "verbs": ["get", "list", "delete"],
        },
        {
            "apiGroups": ["user.openshift.io"],
            "resources": ["users", "identities"],
            "verbs": ["get", "list", "delete"],
        },
    ]


def test_identity_reconciler_is_enabled_after_controlled_live_certification() -> None:
    documents = _documents()
    cronjob = next(item for item in documents if item["kind"] == "CronJob")

    assert cronjob["spec"]["suspend"] is False


def test_identity_reconciler_delete_permission_is_admission_bounded() -> None:
    documents = _documents()
    policy = next(item for item in documents if item["kind"] == "ValidatingAdmissionPolicy")
    expression = policy["spec"]["validations"][0]["expression"]

    assert "launchpad-participant-identity-reconciler" in expression
    assert "oldObject.userName.startsWith('lp-')" in expression
    assert "oldObject.metadata.name.startsWith('lp-')" in expression
    assert "oldObject.user.name.startsWith('lp-')" in expression


def test_identity_reconciler_requires_out_of_band_keycloak_client_secret() -> None:
    documents = _documents()
    cronjob = next(item for item in documents if item["kind"] == "CronJob")
    environment = {
        item["name"]: item
        for item in cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0][
            "env"
        ]
    }

    assert "value" not in environment["KEYCLOAK_RECONCILER_CLIENT_SECRET"]
    assert (
        environment["KEYCLOAK_RECONCILER_CLIENT_SECRET"]["valueFrom"]["secretKeyRef"]["name"]
        == "launchpad-identity-reconciler-keycloak"
    )
