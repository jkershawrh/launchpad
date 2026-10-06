from __future__ import annotations

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _documents(path: str) -> list[dict]:
    return [x for x in yaml.safe_load_all((ROOT / path).read_text()) if x]


def test_runner_uses_dedicated_identity_and_durable_evidence() -> None:
    docs = _documents("deploy/certification/flightpath/runner-infrastructure.yaml")
    kinds = {(x["kind"], x["metadata"]["name"]): x for x in docs}
    pvc = kinds[("PersistentVolumeClaim", "launchpad-certification-evidence")]
    role = kinds[("ClusterRole", "launchpad-flightpath-certification-runner")]
    build = kinds[("BuildConfig", "launchpad-certification-runner")]
    db_policy = kinds[("NetworkPolicy", "launchpad-certification-postgres-ingress")]
    assert pvc["spec"]["accessModes"] == ["ReadWriteMany"]
    flattened = {(r["apiGroups"][0], tuple(r["resources"]), tuple(r["verbs"])) for r in role["rules"]}
    assert not any("delete" in verbs and "namespaces" in resources for _, resources, verbs in flattened)
    assert not any("create" in verbs and "secrets" in resources for _, resources, verbs in flattened)
    configmap_rule = next(r for r in role["rules"] if r["resources"] == ["configmaps"])
    assert configmap_rule["resourceNames"] == ["default-ingress-cert"]
    assert configmap_rule["verbs"] == ["get"]
    ingress_rule = next(r for r in role["rules"] if r["resources"] == ["ingresses"])
    assert ingress_rule["apiGroups"] == ["config.openshift.io"]
    assert ingress_rule["resourceNames"] == ["cluster"]
    assert ingress_rule["verbs"] == ["get"]
    assert build["spec"]["source"]["type"] == "Git"
    assert len(build["spec"]["source"]["git"]["ref"]) == 40
    assert build["spec"]["output"]["to"] == {
        "kind": "DockerImage",
        "name": "quay.io/rh-ee-jkershaw/launchpad-certification-runner:0e0d947",
    }
    assert build["spec"]["output"]["pushSecret"]["name"] == "launchpad-registry-pull"
    source = db_policy["spec"]["ingress"][0]["from"][0]["podSelector"]["matchLabels"]
    assert source == {"app.kubernetes.io/name": "launchpad-certification-runner"}


def test_job_is_fail_closed_and_binds_candidate_identity() -> None:
    job = _documents("deploy/certification/flightpath/job-template.yaml")[0]
    spec = job["spec"]
    pod = spec["template"]["spec"]
    container = pod["containers"][0]
    init = pod["initContainers"][0]
    env = {x["name"]: x for x in container["env"]}
    assert spec["backoffLimit"] == 0
    assert pod["serviceAccountName"] == "launchpad-certification-runner"
    assert pod["imagePullSecrets"] == [{"name": "launchpad-registry-pull"}]
    assert container["image"] == "__CERTIFICATION_RUNNER_IMAGE__"
    assert init["image"] == "__CERTIFICATION_RUNNER_IMAGE__"
    assert "default-ingress-cert" in init["args"][0]
    assert env["LAUNCHPAD_CA_BUNDLE"]["value"] == "/trust/ca-bundle.crt"
    assert env["LAUNCHPAD_CERTIFICATION_SERVICEACCOUNT"]["value"] == (
        "launchpad-flightpath-candidate:launchpad-certification-runner"
    )
    assert env["LAUNCHPAD_CANDIDATE_GIT_COMMIT"]["value"].startswith("e2d78de")
    assert len(env["LAUNCHPAD_CANDIDATE_MANIFEST_SHA256"]["value"]) == 64
    assert env["LAUNCHPAD_ADMIN_API_KEY"]["valueFrom"]["secretKeyRef"]["name"] == "launchpad-api-keys"
    assert pod["volumes"][0]["persistentVolumeClaim"]["claimName"] == "launchpad-certification-evidence"


def test_admission_policy_pins_probe_binding_subject() -> None:
    docs = _documents("deploy/certification/flightpath/runner-infrastructure.yaml")
    policy = next(x for x in docs if x["kind"] == "ValidatingAdmissionPolicy")
    expression = policy["spec"]["validations"][0]["expression"]
    assert "launchpad-certification-probe" in expression
    assert "launchpad-flightpath-candidate" in expression
    assert "launchpad-certification-runner" in expression
    assert "subjects[0].kind" in expression


def test_certification_container_contains_the_proof_inputs() -> None:
    text = (ROOT / "backend/CertificationContainerfile").read_text()
    assert "COPY certification/" in text
    assert "COPY catalog-onboarding/" in text
    assert "COPY scripts/certify-*-seat.sh" in text
    assert "COPY scripts/certify-cpu-serving-rag.sh" in text
    assert "COPY content-intel-xeon6-agent-201/manifests/" in text
    assert "run_flightpath_certification_matrix.sh" in text


def test_matrix_uses_unique_attempt_prefix_for_idempotent_retries() -> None:
    text = (ROOT / "scripts/run_flightpath_certification_matrix.sh").read_text()
    assert 'run_series="${LAUNCHPAD_RUN_PREFIX:-flightpath-staging}"' in text
    assert "LAUNCHPAD_RUN_ATTEMPT" in text
    assert 'run_prefix="${run_series}-${run_attempt}"' in text


def test_matrix_defaults_to_one_seat_and_requires_an_explicit_scale_override() -> None:
    text = (ROOT / "scripts/run_flightpath_certification_matrix.sh").read_text()

    assert 'certification_seats="${LAUNCHPAD_CERTIFICATION_SEATS:-1}"' in text
    assert '--seats "${certification_seats}"' in text
    assert '--seats 5' not in text
    assert 'run_id="${run_prefix}-${catalog_id}-${certification_seats}-seat"' in text


def test_matrix_covers_every_active_participant_catalog() -> None:
    text = (ROOT / "scripts/run_flightpath_certification_matrix.sh").read_text()
    match = re.search(
        r'LAUNCHPAD_CERTIFICATION_MATRIX:-([^}]*)',
        text,
    )
    assert match is not None
    matrix = set(match.group(1).split())

    active = set()
    for path in (ROOT / "catalog").glob("*/catalog-item.yaml"):
        item = yaml.safe_load(path.read_text())
        if item.get("status") == "active":
            active.add(item.get("catalog_item_id", item.get("id", path.parent.name)))

    assert matrix == active
    assert len(matrix) == 23
