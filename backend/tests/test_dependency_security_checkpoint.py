"""Proof contract for the bounded dependency security checkpoint."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/runs/dependency-security-checkpoint-20260909.json"


def test_patched_dependency_graphs_and_keycloak_candidate_are_pinned():
    root_lock = json.loads((ROOT / "package-lock.json").read_text())
    frontend_lock = json.loads((ROOT / "frontend/package-lock.json").read_text())
    admin_lock = json.loads((ROOT / "admin/package-lock.json").read_text())
    demo_lock = json.loads((ROOT / "demos/frontend/package-lock.json").read_text())

    assert root_lock["packages"]["node_modules/js-yaml"]["version"] == "5.4.1"
    for lock in (frontend_lock, admin_lock, demo_lock):
        assert lock["packages"]["node_modules/vite"]["version"] == "8.2.2"
        assert lock["packages"]["node_modules/postcss"]["version"] == "8.5.28"
    assert frontend_lock["packages"]["node_modules/react-router"]["version"] == "7.18.2"
    assert admin_lock["packages"]["node_modules/react-router"]["version"] == "7.18.3"
    assert demo_lock["packages"]["node_modules/react-router"]["version"] == "7.18.3"
    assert demo_lock["packages"]["node_modules/undici"]["version"] == "7.29.0"
    assert demo_lock["packages"]["node_modules/@vitest/mocker"]["version"] == "4.1.11"

    pom = ElementTree.parse(ROOT / "keycloak-authenticator/pom.xml").getroot()
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    assert pom.findtext("m:properties/m:keycloak.version", namespaces=namespace) == "26.7.0"
    jackson = next(
        dependency
        for dependency in pom.findall("m:dependencies/m:dependency", namespace)
        if dependency.findtext("m:artifactId", namespaces=namespace) == "jackson-databind"
    )
    assert jackson.findtext("m:version", namespaces=namespace) == "2.18.9"

    deployment = (ROOT / "deploy/launchpad/public-access/keycloak.yaml").read_text()
    assert "launchpad-keycloak@sha256:207b8388456f943" in deployment


def test_security_evidence_is_honest_about_the_live_keycloak_boundary():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["result"] == "GREEN-source-and-build-RED-keycloak-live-rollout"
    assert evidence["contains_plaintext_credentials"] is False
    dependabot = evidence["red"]["github_dependabot_open"]
    assert (
        dependabot["critical"]
        + dependabot["high"]
        + dependabot["moderate"]
        + dependabot["low"]
        == dependabot["total"]
        == 105
    )
    assert all(value == 0 for value in evidence["green"]["npm_audit"].values())
    assert evidence["green"]["keycloak_candidate"]["build_result"] == "Complete"
    assert evidence["live_boundary"]["candidate_deployed"] is False
    assert evidence["live_boundary"]["manual_sign_in_certified"] is False


def test_dependency_security_evidence_checksum_is_immutable():
    checksum = Path(f"{EVIDENCE}.sha256")
    expected = checksum.read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected
