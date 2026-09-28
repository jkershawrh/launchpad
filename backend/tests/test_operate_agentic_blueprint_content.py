from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "catalog/operate-agentic-blueprint/catalog-item.yaml"
CONTENT_ROOT = ROOT / "content-operate-agentic-blueprint"


def test_operate_blueprint_is_a_draft_core_401_on_the_canonical_runtime():
    catalog = yaml.safe_load(CATALOG_PATH.read_text())
    metadata = catalog["metadata"]

    assert catalog["catalog_item_id"] == "operate-agentic-blueprint"
    assert catalog["status"] == "draft"
    assert metadata["learning_level"] == "401"
    assert metadata["learning_stage"] == "Operate"
    assert metadata["journey_role"] == "core"
    assert metadata["shared_blueprint"] == "red-hat-intel-agentic-v1"
    assert metadata["max_workshop_seats"] == 1
    assert metadata["public_max_workshop_seats"] == 1
    assert metadata["promotion_sequence"] == [1, 5, 25]
    assert metadata["package_base_commit"] == (
        "272bcea5889ef761a3e1cb54103861534b69e807"
    )
    assert metadata["flightpath_deployment_overlay_commit"] == (
        "d7c7e686d6513a77de685569b27863c9269c990f"
    )
    assert metadata["prerequisites"] == ["multi-agent-quickstart"]
    assert metadata["workload_deploy_path"] == "deploy/workloads/multi-agent-seat"
    assert metadata["namespace_slug"] == "agentic-ops"
    assert re.fullmatch(r"[0-9a-f]{40}", metadata["workload_revision"])
    assert metadata["workload_revision"] != "5292234017bf3f538767e6b6a3c627d146fca086"
    assert metadata["runtime_source_revision"] == (
        "de864e8a97c89d43138af338ca38df16bdf0577a"
    )
    assert metadata["workload_helm_values"]["image"]["digest"].startswith("sha256:")
    assert re.fullmatch(r"[0-9a-f]{40}", metadata["showroom_content_ref"])
    assert metadata["source_content_revision"] == metadata["showroom_content_ref"]
    presentation = metadata["presentation"]
    assert re.fullmatch(r"[0-9a-f]{40}", presentation["revision"])
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", presentation["image"]["digest"])
    assert presentation["revision"] == "9cec3cebe7972b92385c55174674532eeb895f97"
    assert presentation["image"] == {
        "repository": "quay.io/rh-ee-jkershaw/launchpad-operate-agentic-blueprint-presentation",
        "digest": "sha256:2aee08aaac09e296725954a9450ffc87240b9a9ef458a291916127871259c580",
    }
    assert presentation["runtime_configuration"] == {
        "api_mode": "same-origin-proxy",
        "api_path": "/api",
        "api_upstream": "http://multi-agent:8000",
        "lab_handoff": "showroom",
    }
    assert metadata["workload_helm_values"]["presentation"] == {
        "enabled": True,
        "image": presentation["image"],
        "apiUpstream": "http://multi-agent:8000",
        "ingressDomain": "apps.flightpath.fm2aihpcsed.com",
    }
    assert metadata["workload_routes"]["presentation"] == "story"
    assert metadata["showroom_antora_flat"] is True
    presentation_tab = next(
        tab for tab in metadata["showroom_tabs"] if tab["id"] == "presentation"
    )
    assert presentation_tab["source"] == "workload.route.presentation"
    assert metadata["seat_pods"] == 3
    assert metadata["workload_helm_values"]["image"] == {
        "repository": "ghcr.io/jkershawrh/multi-agent-quickstart",
        "digest": "sha256:72bf1862421846f8d0ed1cd56e5b10d4241d009e9624dcfd948dd42e59ec01ea",
    }
    assert metadata["workload_helm_values"]["imagePullSecrets"] == [
        {"name": "launchpad-registry-pull"}
    ]
    assert metadata["activation_blockers"]


def test_operate_blueprint_content_is_a_linear_evidence_journey():
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    nav = (CONTENT_ROOT / "modules/ROOT/nav.adoc").read_text()
    expected = [
        "index.adoc",
        "01-baseline.adoc",
        "02-correlate.adoc",
        "03-policy.adoc",
        "04-failure-recovery.adoc",
        "05-change-proof.adoc",
        "99-conclusion.adoc",
    ]
    assert [
        line.split("xref:", 1)[1].split("[", 1)[0]
        for line in nav.splitlines()
        if "xref:" in line
    ] == expected

    guide = "\n".join((pages / name).read_text() for name in expected)
    for proof in (
        "journey ID",
        "Supporting Evidence",
        "policy",
        "Prompt in",
        "Response out",
        "Intel Xeon",
        "human review",
        "REHEARSAL",
    ):
        assert proof in guide


def test_operate_blueprint_does_not_present_uncertified_integrations_as_live():
    pages = CONTENT_ROOT / "modules/ROOT/pages"
    guide = "\n".join(path.read_text() for path in sorted(pages.glob("*.adoc")))

    assert "not deployed in this draft" in guide
    assert "OpenTelemetry" in guide
    assert "Kagenti" in guide
    assert "MLflow" not in guide
    assert "mortgage" not in guide.lower()


def test_operate_blueprint_playbook_uses_local_content():
    playbook = yaml.safe_load((ROOT / "site-operate-agentic-blueprint.yml").read_text())
    component = yaml.safe_load((CONTENT_ROOT / "antora.yml").read_text())

    assert playbook["content"]["sources"] == [
        {"url": ".", "start_path": "content-operate-agentic-blueprint"}
    ]
    assert component["asciidoc"]["attributes"]["project_name"] == "%namespace%"


def test_flightpath_mounts_the_operate_catalog_from_source_control():
    overlay = ROOT / "deploy/launchpad/overlays/flightpath-candidate"
    kustomization = yaml.safe_load((ROOT / "catalog/kustomization.yaml").read_text())
    generated = {
        item["name"]: item.get("files", [])
        for item in kustomization["configMapGenerator"]
    }
    assert generated["canonical-operate-agentic-blueprint-catalog"] == [
        "catalog-item.yaml=operate-agentic-blueprint/catalog-item.yaml"
    ]

    documents = list(yaml.safe_load_all((overlay / "patch-runtime.yaml").read_text()))
    for deployment_name in ("backend", "lifecycle-worker"):
        deployment = next(
            item for item in documents if item["metadata"]["name"] == deployment_name
        )
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(
            item for item in pod_spec["containers"] if item["name"] == deployment_name
        )
        mount = next(
            item
            for item in container["volumeMounts"]
            if item["name"] == "canonical-operate-agentic-blueprint-catalog"
        )
        assert mount["mountPath"] == (
            "/opt/catalog/operate-agentic-blueprint/catalog-item.yaml"
        )
        volume = next(
            item
            for item in pod_spec["volumes"]
            if item["name"] == "canonical-operate-agentic-blueprint-catalog"
        )
        assert volume["configMap"]["name"] == (
            "canonical-operate-agentic-blueprint-catalog"
        )
