from __future__ import annotations

from pathlib import Path

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
    assert build["spec"]["source"]["type"] == "Git"
    assert len(build["spec"]["source"]["git"]["ref"]) == 40
    assert build["spec"]["output"]["to"] == {
        "kind": "DockerImage",
        "name": "quay.io/rh-ee-jkershaw/launchpad-certification-runner:f18f06c",
    }
    assert build["spec"]["output"]["pushSecret"]["name"] == "launchpad-registry-pull"
    source = db_policy["spec"]["ingress"][0]["from"][0]["podSelector"]["matchLabels"]
    assert source == {"app.kubernetes.io/name": "launchpad-certification-runner"}


def test_job_is_fail_closed_and_binds_candidate_identity() -> None:
    job = _documents("deploy/certification/flightpath/job-template.yaml")[0]
    spec = job["spec"]
    pod = spec["template"]["spec"]
    container = pod["containers"][0]
    env = {x["name"]: x for x in container["env"]}
    assert spec["backoffLimit"] == 0
    assert pod["serviceAccountName"] == "launchpad-certification-runner"
    assert pod["imagePullSecrets"] == [{"name": "launchpad-registry-pull"}]
    assert container["image"] == "__CERTIFICATION_RUNNER_IMAGE__"
    assert env["LAUNCHPAD_CANDIDATE_GIT_COMMIT"]["value"].startswith("e2d78de")
    assert len(env["LAUNCHPAD_CANDIDATE_MANIFEST_SHA256"]["value"]) == 64
    assert env["LAUNCHPAD_ADMIN_API_KEY"]["valueFrom"]["secretKeyRef"]["name"] == "launchpad-api-keys"
    assert pod["volumes"][0]["persistentVolumeClaim"]["claimName"] == "launchpad-certification-evidence"


def test_certification_container_contains_the_proof_inputs() -> None:
    text = (ROOT / "backend/CertificationContainerfile").read_text()
    assert "COPY certification/" in text
    assert "COPY catalog-onboarding/" in text
    assert "COPY scripts/certify-*-seat.sh" in text
    assert "run_flightpath_certification_matrix.sh" in text
