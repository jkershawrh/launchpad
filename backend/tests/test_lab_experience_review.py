from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "evidence/lab-experience-review-20260930.yaml"
REQUIRED_SECTIONS = {
    "story",
    "show",
    "learn",
    "do",
    "prove",
    "operators",
    "inference",
    "cleanup",
}
COMPATIBILITY_ALIASES = {"cpu-inference-serving", "rag-on-xeon"}
PLATFORM_VALIDATION = {"smoke-test"}


def _portfolio_catalog_ids() -> set[str]:
    included: set[str] = set()
    for path in (ROOT / "catalog").glob("*/catalog-item.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if document.get("status") != "deprecated":
            included.add(str(document["catalog_item_id"]))
    return included


def test_experience_review_covers_all_25_non_deprecated_catalog_items() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))

    assert len(_portfolio_catalog_ids()) == 25
    assert set(review["labs"]) == _portfolio_catalog_ids()
    assert review["portfolio_scope"]["included_statuses"] == ["active", "draft"]
    assert review["portfolio_scope"]["excluded_statuses"] == ["deprecated"]
    assert review["portfolio_scope"]["distinct_learning_experience_count"] == 23
    assert review["portfolio_scope"]["participant_learning_experience_count"] == 22
    assert review["portfolio_scope"]["platform_validation_experience_count"] == 1
    assert review["portfolio_scope"]["compatibility_alias_count"] == 2


def test_each_participant_lab_records_the_full_experience_contract() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))

    for catalog_id, lab in review["labs"].items():
        assert lab["display_name"], catalog_id
        assert lab["overall_status"], catalog_id
        assert lab["next_action"], catalog_id
        if catalog_id in COMPATIBILITY_ALIASES | PLATFORM_VALIDATION:
            continue
        assert REQUIRED_SECTIONS <= set(lab), catalog_id
        for section in REQUIRED_SECTIONS:
            assert lab[section]["status"], (catalog_id, section)
            assert lab[section]["evidence"], (catalog_id, section)


def test_aliases_and_platform_smoke_are_not_misrepresented_as_learning_labs() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))

    for catalog_id in COMPATIBILITY_ALIASES:
        lab = review["labs"][catalog_id]
        assert lab["overall_status"] == "compatibility-alias-hidden"
        assert all(lab[section]["status"] == "duplicate" for section in REQUIRED_SECTIONS)

    smoke = review["labs"]["smoke-test"]
    assert smoke["overall_status"] == "platform-validation-only"
    for section in ("story", "show", "learn", "operators", "inference"):
        assert smoke[section]["status"] == "not-applicable"


def test_review_names_and_contract_links_match_the_canonical_catalog() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))

    for catalog_id, lab in review["labs"].items():
        catalog_path = ROOT / f"catalog/{catalog_id}/catalog-item.yaml"
        catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        metadata = catalog.get("metadata") or {}
        assert lab["display_name"] == catalog["display_name"], catalog_id

        onboarding_candidates = list((ROOT / "catalog-onboarding").glob(f"{catalog_id}*.yaml"))
        if onboarding_candidates:
            onboarding_ref = metadata.get("onboarding_contract")
            assert onboarding_ref and (ROOT / onboarding_ref).is_file(), catalog_id
            intake = yaml.safe_load((ROOT / onboarding_ref).read_text(encoding="utf-8"))
            assert intake["catalog"]["catalog_item_id"] == catalog_id

        certification_candidates = list((ROOT / "certification/catalog").glob(f"{catalog_id}*.yaml"))
        if certification_candidates:
            certification_ref = metadata.get("certification_proof_contract")
            assert certification_ref and (ROOT / certification_ref).is_file(), catalog_id
            contract = yaml.safe_load((ROOT / certification_ref).read_text(encoding="utf-8"))
            assert contract["metadata"]["catalog_item_id"] == catalog_id


def test_intel_agent_showroom_pin_matches_its_onboarding_source() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog/intel-xeon6-agent-201/catalog-item.yaml").read_text(encoding="utf-8")
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/intel-xeon6-agent-201.yaml").read_text(encoding="utf-8")
    )

    assert catalog["metadata"]["showroom_content_repo_url"] == intake["sources"]["showroom"]["repo_url"]
    assert catalog["metadata"]["showroom_content_ref"] == intake["sources"]["showroom"]["revision"]


def test_every_participant_lab_has_a_probe_and_lifecycle_proof_contract() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    participant_ids = set(review["labs"]) - COMPATIBILITY_ALIASES - PLATFORM_VALIDATION

    for catalog_id in participant_ids:
        catalog = yaml.safe_load(
            (ROOT / f"catalog/{catalog_id}/catalog-item.yaml").read_text(encoding="utf-8")
        )
        contract_path = ROOT / catalog["metadata"]["certification_proof_contract"]
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        spec = contract["spec"]
        assert spec["seat_probe"]["argv"], catalog_id
        assert spec["seat_probe"]["json_assertions"], catalog_id
        assert spec["cleanup"]["resources"], catalog_id
        rubric_categories = {category["id"] for category in spec["rubric"]["categories"]}
        assert rubric_categories & {"cleanup", "lifecycle"}, catalog_id


def test_review_standard_preserves_show_learn_do_prove_order() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))

    assert review["review_standard"]["journey_order"] == [
        "show",
        "learn",
        "do",
        "prove",
    ]


def test_sovereign_201_exact_release_requires_live_inference_recertification() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    lab = review["labs"]["sovereign-ai-201"]
    catalog = yaml.safe_load(
        (ROOT / "catalog/sovereign-ai-201/catalog-item.yaml").read_text(
            encoding="utf-8"
        )
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/sovereign-ai-201.yaml").read_text(
            encoding="utf-8"
        )
    )
    contract = yaml.safe_load(
        (ROOT / "certification/catalog/sovereign-ai-201.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert lab["overall_status"] == "one-seat-live-certified-active"
    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert catalog["metadata"]["certification_stage"] == (
        intake["certification"]["stage"]
    ) == "1-seat-certified"
    assert intake["certification"]["certified_seats"] == 1
    assert intake["sources"]["workload"]["revision"] == (
        "0fdcfba6c2db35190a768e561ac6b0665c76484b"
    )
    assert intake["sources"]["showroom"]["revision"] == (
        "0fdcfba6c2db35190a768e561ac6b0665c76484b"
    )
    assert intake["sources"]["showroom"]["playbook"] == (
        "showroom/default-site.yml"
    )
    assert catalog["metadata"]["showroom_content_repo_url"].startswith(
        "https://github.com/"
    )
    assert catalog["metadata"]["workload_repo"].startswith("https://github.com/")
    values = intake["runtime"]["workload"]["helm_values"]
    assert values["adapter"]["mode"] == "live"
    assert values["adapter"]["dnsEgressCIDR"] == "10.128.0.0/14"
    assert values["adapter"]["policy"]["approvedModels"] == (
        "granite-3.2-8b-tools"
    )
    assert values["adapter"]["model"]["egressNamespace"] == (
        "launchpad-flightpath-candidate"
    )
    assert values["adapter"]["model"]["egressPodName"] == (
        "launchpad-candidate-maas"
    )
    assert values["adapter"]["model"]["egressPort"] == 4000
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    assert {"path": "journey.mode", "equals": "LIVE"} in assertions
    assert {"path": "journey.model_participated", "equals": True} in assertions
    assert {"path": "journey.model", "equals": "granite-3.2-8b-tools"} in assertions


def test_virtualization_301_pins_public_root_playbook_without_claiming_certification() -> None:
    exact_revision = "1c4669bfc07df84a1b304c7eebdceb793ad0f949"
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))["labs"][
        "virtualization-ai-301"
    ]
    catalog = yaml.safe_load(
        (ROOT / "catalog/virtualization-ai-301/catalog-item.yaml").read_text(
            encoding="utf-8"
        )
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/virtualization-ai-301.yaml").read_text(
            encoding="utf-8"
        )
    )
    metadata = catalog["metadata"]

    assert catalog["status"] == intake["catalog"]["status"] == "draft"
    assert intake["certification"]["certified_seats"] == 0
    assert metadata["showroom_content_ref"] == exact_revision
    assert metadata["source_content_revision"] == exact_revision
    assert metadata["workload_revision"] == exact_revision
    assert intake["sources"]["showroom"]["revision"] == exact_revision
    assert intake["sources"]["workload"]["revision"] == exact_revision
    assert metadata["showroom_content_playbook"] == "default-site.yml"
    assert intake["sources"]["showroom"]["playbook"] == "default-site.yml"
    for source in intake["sources"].values():
        assert source["repo_url"].startswith("https://github.com/")
        assert source["gitops_repo_url"].startswith("https://github.com/")
    assert metadata["workload_repo"].startswith("https://github.com/")
    assert "capture-platform-owned-intel-placement-receipt" in metadata[
        "activation_blockers"
    ]
    assert metadata["activation_blockers"] == intake["certification"][
        "activation_blockers"
    ]
    assert review["source_state"]["catalog_pinned_revision"] == exact_revision
    assert review["source_state"]["runtime_image_source_revision"] == (
        "eaca0d12a224c6edebeae6c0a4f80c9fd92bfdf1"
    )
    assert review["source_state"]["showroom_content_status"] == (
        "exact-public-git-root-playbook-pinned-not-live-certified"
    )


def test_multi_agent_301_exact_release_requires_story_and_correlation_recertification() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    lab = review["labs"]["multi-agent-quickstart"]
    catalog = yaml.safe_load(
        (ROOT / "catalog/multi-agent-quickstart/catalog-item.yaml").read_text(
            encoding="utf-8"
        )
    )
    intake = yaml.safe_load(
        (
            ROOT
            / "catalog-onboarding/multi-agent-quickstart-flightpath.yaml"
        ).read_text(encoding="utf-8")
    )
    contract = yaml.safe_load(
        (
            ROOT
            / "certification/catalog/multi-agent-quickstart-flightpath.yaml"
        ).read_text(encoding="utf-8")
    )

    assert lab["overall_status"] == "one-seat-live-certified-active"
    assert catalog["status"] == intake["catalog"]["status"] == "active"
    assert catalog["metadata"]["certification_stage"] == (
        intake["certification"]["stage"]
    ) == "1-seat-certified"
    assert intake["certification"]["max_workshop_seats"] == 1
    assert intake["references"]["original_lab"]["revision"] == (
        "fd6affb22691236f6e0c7ff13abd2a8c0829453e"
    )
    values = intake["runtime"]["workload"]["helm_values"]
    assert values["image"] == {
        "repository": "ghcr.io/jkershawrh/multi-agent-quickstart",
        "digest": "sha256:67184f0bd18f29146f9353d2f80108c5d62e6bf9f866c01000b8762449812eb1",
    }
    assert values["presentation"]["enabled"] is True
    assert [tab["id"] for tab in intake["runtime"]["tabs"]] == [
        "presentation",
        "terminal",
        "workspace",
        "openshift-console",
    ]
    assert contract["spec"]["seat_probe"]["argv"][1] == (
        "scripts/certify-multi-agent-301-seat.sh"
    )
    wrapper = (ROOT / "scripts/certify-multi-agent-301-seat.sh").read_text()
    assert "PRESENTATION_REQUIRED=true" in wrapper
    assert "CORRELATION_REQUIRED=true" in wrapper


def test_advanced_and_virtualization_labs_pin_their_exact_releases() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    expected = {
        "agentic-ai-601": {
            "revision": "22f4e4656843721c66b0779e52c30fc46a4061de",
            "presentation": "sha256:4442f16d4d401c376a86dbcfa0acc111abf78c8cd0668f149adb41a6dc35192e",
            "workload": "sha256:5a80d8c2a5f3031c2c90e3b0059123633a2984d54344ab6e964a21b9b537fafc",
        },
        "virtualization-ai-501": {
            "revision": "6e65858f773e2a28a4874a2a59785e8c8ab52b07",
            "presentation": "sha256:06e5e51b88f561bd401dd634acdcc07e3c6112caf4316fb46c989ac8baf3f762",
            "workload": "sha256:e14a5dc17dfb1a63321a99d4e76ad904dd271e5fb57b359c62c263891b8173bf",
        },
        "virtualization-ai-401": {
            "revision": "f00b4bc075acf37f014b8ee55d5810625639b6b3",
            "presentation": "sha256:7115b9332335e9ceb77f68b9dc04828b36e1f0c874deee56272556fa3001bf25",
            "workload": "sha256:864ad89cb5f4bae6f2b403c31604d78692e30afe9275c0d753a9eafaeae9d8ca",
        },
    }

    for catalog_id, release in expected.items():
        catalog = yaml.safe_load(
            (ROOT / f"catalog/{catalog_id}/catalog-item.yaml").read_text()
        )
        intake = yaml.safe_load(
            (ROOT / f"catalog-onboarding/{catalog_id}.yaml").read_text()
        )
        metadata = catalog["metadata"]

        expected_status = (
            "active"
            if catalog_id in {"virtualization-ai-401", "virtualization-ai-501"}
            else "draft"
        )
        expected_stage = (
            "1-seat-certified"
            if catalog_id in {"virtualization-ai-401", "virtualization-ai-501"}
            else "immutable-source-published"
        )
        assert catalog["status"] == intake["catalog"]["status"] == expected_status
        assert metadata["certification_stage"] == (
            intake["certification"]["stage"]
        ) == expected_stage
        assert metadata["workload_revision"] == release["revision"]
        assert metadata["showroom_content_ref"] == release["revision"]
        assert intake["sources"]["workload"]["revision"] == release["revision"]
        assert intake["sources"]["showroom"]["revision"] == release["revision"]
        assert release["presentation"] in str(metadata["workload_helm_values"])
        assert release["workload"] in str(metadata["workload_helm_values"])
        expected_overall = {
            "virtualization-ai-401": "one-seat-live-certified-active",
            "virtualization-ai-501": "one-seat-live-certified-active",
            "agentic-ai-601": "immutable-source-published-draft",
        }[catalog_id]
        assert review["labs"][catalog_id]["overall_status"] == expected_overall

    virtualization_401 = review["labs"]["virtualization-ai-401"]["source_state"]
    assert virtualization_401["published_revision"] == (
        "f00b4bc075acf37f014b8ee55d5810625639b6b3"
    )
    assert virtualization_401["catalog_pinned_revision"] == (
        "f00b4bc075acf37f014b8ee55d5810625639b6b3"
    )
    assert virtualization_401["publication_workflow"] == (
            "https://github.com/jkershawrh/virtualization-ai-401/actions/runs/36761503526"
    )
    assert virtualization_401["immutable_images"] == {
        "presentation": "ghcr.io/jkershawrh/virtualization-ai-401-presentation@sha256:7115b9332335e9ceb77f68b9dc04828b36e1f0c874deee56272556fa3001bf25",
        "operations_adapter": "ghcr.io/jkershawrh/virtualization-ai-401-operations-adapter@sha256:864ad89cb5f4bae6f2b403c31604d78692e30afe9275c0d753a9eafaeae9d8ca",
    }


def test_virtualization_501_generated_route_label_fits_openshift_limit() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog/virtualization-ai-501/catalog-item.yaml").read_text()
    )
    metadata = catalog["metadata"]
    namespace = f"launchpad-flightpath-candida-{metadata['namespace_slug']}-ffffff"
    generated_label = f"{metadata['workload_routes']['ui']}-{namespace}"

    assert len(generated_label) <= 63


def test_virtualization_401_certification_capabilities_match_flightpath() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog/virtualization-ai-401/catalog-item.yaml").read_text()
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/virtualization-ai-401.yaml").read_text()
    )
    contract = yaml.safe_load(
        (ROOT / "certification/catalog/virtualization-ai-401.yaml").read_text()
    )
    showroom_paths = [page["path"] for page in contract["spec"]["showroom"]["pages"]]
    assert showroom_paths == [
        "/www/virtualization-ai-401/index.html",
        "/www/virtualization-ai-401/02-preflight.html",
        "/www/virtualization-ai-401/06-validate.html",
    ]
    assert catalog["metadata"]["workload_helm_values"]["presentation"][
        "ingressDomain"
    ] == "apps.flightpath.fm2aihpcsed.com"
    assert intake["runtime"]["workload"]["helm_values"]["presentation"][
        "ingressDomain"
    ] == "apps.flightpath.fm2aihpcsed.com"
    cluster_document = yaml.safe_load(
        (
            ROOT
            / "deploy/launchpad/overlays/flightpath-candidate/candidate-clusters.yaml"
        ).read_text()
    )
    flightpath = yaml.safe_load(cluster_document["data"]["clusters.yaml"])[
        "clusters"
    ][0]

    required = catalog["required_capabilities"]
    assert required == intake["runtime"]["required_capabilities"]
    assert set(required).issubset(set(flightpath["capabilities"]))
    assert "openshift-virtualization" in required
    assert "openshift_virtualization" not in required
    assert catalog["metadata"]["required_models"] == []
    values = catalog["metadata"]["workload_helm_values"]
    assert values == intake["runtime"]["workload"]["helm_values"]
    assert values["presentation"]["image"]["repository"] == (
        "ghcr.io/jkershawrh/virtualization-ai-401-presentation"
    )
    assert values["operationsAdapter"]["image"]["repository"] == (
        "ghcr.io/jkershawrh/virtualization-ai-401-operations-adapter"
    )
    assert values["operationsAdapter"]["mode"] == "rehearsal"
    assert values["operationsAdapter"]["ledger"]["storageClassName"] == (
        "ocs-storagecluster-ceph-rbd"
    )
    assert "presentation_image" not in values
    assert "operations_adapter_image" not in values


def test_virtualization_501_truthful_rehearsal_does_not_allocate_a_model_secret() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog/virtualization-ai-501/catalog-item.yaml").read_text()
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/virtualization-ai-501.yaml").read_text()
    )

    metadata = catalog["metadata"]
    runtime = intake["runtime"]
    assert metadata["required_models"] == runtime["required_models"] == []
    assert metadata["inference_endpoint"] == "none"
    assert metadata["workload_runtime_secret_name"] == ""
    assert metadata["workload_runtime_secret_sources"] == {}
    assert runtime["workload"]["runtime_secret_name"] == ""
    assert runtime["workload"]["runtime_secret_sources"] == {}
    assert catalog["required_capabilities"] == runtime["required_capabilities"] == [
        "openshift",
        "openshift-virtualization",
        "showroom",
    ]
    assert metadata["showroom_content_repo_url"].startswith("https://github.com/")
    assert metadata["workload_repo"].startswith("https://github.com/")
    contract = yaml.safe_load(
        (ROOT / "certification/catalog/virtualization-ai-501.yaml").read_text()
    )
    assert [page["path"] for page in contract["spec"]["showroom"]["pages"]] == [
        "/www/virtualization-ai-501/index.html",
        "/www/virtualization-ai-501/01-discover.html",
        "/www/virtualization-ai-501/06-qualify.html",
    ]


def test_applied_lab_reviews_separate_live_proof_from_local_source_updates() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    expected_states = {
        "network-operations-agent": {
            "revision": "6ed5c53337afa55c03949b2963b429f32977ef69",
            "overall": "one-seat-live-certified-active",
            "cleanup": "green-live",
            "change_state": "one-seat-live-certified",
        },
            "hybrid-fraud-detection": {
                "revision": "9dccae859e939d836c06cc9fb51d8ae4a848a38f",
                "overall": "security-remediation-required-draft",
                "cleanup": "green-local",
                "change_state": "committed-published-pinned-not-live-certified",
            },
        "agent-reliability": {
            "revision": "9c69348c34904c58997318d9124ac3d50661984b",
            "overall": "source-update-published-draft",
            "cleanup": "green-local",
            "change_state": "committed-published-pinned-not-live-certified",
        },
    }

    for catalog_id, expected in expected_states.items():
        lab = review["labs"][catalog_id]
        source_state = lab["source_state"]

        assert lab["overall_status"] == expected["overall"]
        assert lab["cleanup"]["status"] == expected["cleanup"]
        assert source_state["catalog_pinned_revision"] == expected["revision"]
        assert source_state["post_review_changes"] == expected["change_state"]
        assert source_state["post_review_paths"]
        assert source_state["local_validation"]["status"] == "green-local"

        evidence_path = ROOT / source_state["five_seat_live_evidence"]
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["catalog_item_id"] == catalog_id
        assert evidence["result"] == "GREEN-live"
        assert evidence["order"]["cluster_ref"] == "flightpath"
        assert evidence["order"]["seat_count"] == 5
        assert evidence["order"]["status_before_reclaim"] == "ready"
        assert evidence["rubric"]["score"] == 100
        assert evidence["cleanup"]["status"] == "completed"
        assert evidence["cleanup"]["model_keys_revoked"] is True
        assert all(
            count == 0 for count in evidence["cleanup"]["resource_counts"].values()
        )

    reliability = review["labs"]["agent-reliability"]
    assert reliability["prove"]["status"] == "conditional"
    assert reliability["operators"]["status"] == "green-local"
    assert reliability["inference"]["status"] == "conditional"


def test_agent_reliability_records_verified_registry_mirror_provenance() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    provenance = review["labs"]["agent-reliability"]["source_state"][
        "image_provenance"
    ]

    assert provenance["status"] == "verified-byte-identical-mirror"
    assert provenance["manifest_digest"] == (
        "sha256:604331d4a050f47457e27c2191106aa3fa075d408514143cd9eac6da18dfc3fb"
    )
    assert provenance["config_digest"] == (
        "sha256:62275b5e05c96d695019c85a16bbf208c97cdeb24320af03863d9b5af1b3dbfc"
    )
    assert provenance["image_source_revision"] == (
        "4cf610d3c225c8b31a73354bb405a3f9022305a2"
    )
    assert provenance["source_manifest_registry"] == "quay.io"
    assert provenance["catalog_registry"] == "ghcr.io"
    assert provenance["ghcr_visibility"] == "public"


def test_sovereign_101_records_exact_published_source_and_live_proof() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    lab = review["labs"]["sovereign-ai-101"]
    release = lab["release"]

    assert lab["overall_status"] == "one-seat-live-certified-active"
    assert lab["candidate_revision"] == (
        "6d7c6f267407d42ca465b8a381d841d8b5b77567"
    )
    assert release["status"] == "published-live-certified"
    assert release["workflow"].endswith("/actions/runs/36765624274")
    assert release["presentation_image"].endswith(
        "@sha256:c9301b53eca8b8a20c9f87d142363b7c9b0f2abffeb36fd6b97ee3ebb895ec2d"
    )
    assert release["rehearsal_image"].endswith(
        "@sha256:c7f5058213960ceb1a268506f43fe666c4cf5df62ce7d6e444dd277b34886958"
    )


def test_learning_pipeline_classifies_every_portfolio_item_once() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    tracks = review["learning_pipeline"]
    classified = [catalog_id for catalog_ids in tracks.values() for catalog_id in catalog_ids]

    assert len(classified) == len(set(classified))
    assert set(classified) == set(review["labs"])

    for track in ("agentic_ai", "sovereign_ai", "virtualization_ai"):
        levels = []
        for catalog_id in tracks[track]:
            catalog = yaml.safe_load(
                (ROOT / f"catalog/{catalog_id}/catalog-item.yaml").read_text(
                    encoding="utf-8"
                )
            )
            levels.append(int(catalog["metadata"]["learning_level"]))
        assert levels == sorted(levels), (track, levels)


def test_virtualization_foundations_records_exact_one_seat_proof_before_activation() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog/virtualization-ai-foundations-101/catalog-item.yaml").read_text(
            encoding="utf-8"
        )
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/virtualization-ai-foundations-101.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert catalog["status"] == "active"
    assert catalog["metadata"]["certification_stage"] == "1-seat-certified"
    assert catalog["metadata"]["workload_runtime_value_bindings"] == {
        "vm.sshAuthorizedKey": "VM_SSH_PUBLIC_KEY"
    }
    assert (
        catalog["metadata"]["workload_runtime_secret_sources"]["VM_SSH_PRIVATE_KEY"]
        == {
            "source": "generated_ssh_keypair",
            "pair": "operations-vm",
            "part": "private",
        }
    )
    assert catalog["metadata"]["activation_blockers"] == []
    assert intake["catalog"]["status"] == "active"
    assert intake["certification"]["certified_seats"] == 1
    assert catalog["metadata"]["showroom_content_ref"] == intake["sources"][
        "showroom"
    ]["revision"] == "e74393d0def1a7a2749911b3a421c62f3f1c2558"
    assert catalog["metadata"]["showroom_content_image"] == intake["sources"][
        "showroom"
    ]["content_image"]
    assert catalog["metadata"]["workload_helm_values"] == intake["runtime"][
        "workload"
    ]["helm_values"]

    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))["labs"][
        "virtualization-ai-foundations-101"
    ]
    assert review["overall_status"] == "exact-revision-one-seat-certified-active"
    assert review["candidate_revision"] == (
        "e74393d0def1a7a2749911b3a421c62f3f1c2558"
    )
    assert review["launchpad_backend_candidate"] == {
        "branch": "codex/virt101-backend-keypair",
        "revision": "b5c38364ce556fbf0c40de07ec25c209357f3d0c",
        "workflow": "https://github.com/rhpds/launchpad/actions/runs/36727202035",
        "image": "ghcr.io/rhpds/launchpad-backend@sha256:5349f3538f9abfc77f927c6df5ac747be2b736cbe7290539b6ca5db39eec993f",
        "status": "published-not-deployed",
        "supply_chain_evidence": {
            "sbom": "published",
            "signature": "published",
            "provenance_attestation": "published",
            "fixable_high_critical_findings": 0,
            "nonfixable_high_inventory_findings": 53,
            "critical_inventory_findings": 0,
        },
    }
    assert review["immutable_images"]["adapter"] == intake["runtime"]["workload"][
        "helm_values"
    ]["workload_image"]
    assert review["immutable_images"]["presentation"] == intake["runtime"][
        "workload"
    ]["helm_values"]["presentation_image"]
    assert review["immutable_images"]["showroom_content"] == intake["sources"][
        "showroom"
    ]["content_image"]
    assert review["live_certification"]["result"] == "GREEN-live"
    assert review["live_certification"]["rubric_score"] == 100
    assert review["live_certification"]["evidence"].endswith(
        "flightpath-live-20261001-virtualization-ai-101-1seat-r10.json"
    )

    certifier = (ROOT / "scripts/certify-virtualization-ai-seat.sh").read_text(
        encoding="utf-8"
    )
    contract = yaml.safe_load(
        (ROOT / "certification/catalog/virtualization-ai-foundations-101.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert "terminal_vm_request" in certifier
    assert "VM_SSH_PRIVATE_KEY" in certifier
    assert "/usr/local/bin/virtualization-ai-client" in certifier
    assert {"path": "journey.request_origin", "equals": "operations-vm"} in contract[
        "spec"
    ]["seat_probe"]["json_assertions"]


def test_canonical_cpu_serving_catalog_matches_its_flightpath_onboarding_contract() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog/intel-llm-cpu-serving/catalog-item.yaml").read_text(
            encoding="utf-8"
        )
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/intel-llm-cpu-serving.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert catalog["version"] == intake["catalog"]["version"]
    assert catalog["status"] == intake["catalog"]["status"]
    assert (
        catalog["metadata"]["workshop_cluster_ref"]
        == intake["runtime"]["workshop_cluster_ref"]
        == "flightpath"
    )
    assert (
        catalog["metadata"]["inference_endpoint"]
        == intake["runtime"]["inference_endpoint"]
        == "direct_vllm_candidate"
    )
    assert catalog["metadata"]["showroom_content_repo_url"] == intake["sources"][
        "showroom"
    ]["repo_url"]
    assert catalog["metadata"]["showroom_content_ref"] == intake["sources"][
        "showroom"
    ]["revision"]
    assert catalog["metadata"]["source_content_repo"] == intake["sources"][
        "showroom"
    ]["repo_url"]
    assert catalog["metadata"]["source_content_revision"] == intake["sources"][
        "showroom"
    ]["revision"]
    assert catalog["metadata"]["workload_repo"] == intake["sources"]["workload"][
        "repo_url"
    ]
    assert catalog["metadata"]["workload_revision"] == intake["sources"][
        "workload"
    ]["revision"]
    assert catalog["metadata"]["certification_stage"] == intake["certification"][
        "stage"
    ]
    assert catalog["metadata"]["max_workshop_seats"] == intake["certification"][
        "max_workshop_seats"
    ]
    assert catalog["metadata"]["promotion_sequence"] == intake["certification"][
        "promotion_sequence"
    ]


def test_canonical_multi_agent_catalog_matches_its_flightpath_onboarding_contract() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog/multi-agent-quickstart/catalog-item.yaml").read_text(
            encoding="utf-8"
        )
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/multi-agent-quickstart-flightpath.yaml").read_text(
            encoding="utf-8"
        )
    )
    metadata = catalog["metadata"]
    runtime = intake["runtime"]

    assert catalog["version"] == intake["catalog"]["version"]
    assert catalog["status"] == intake["catalog"]["status"]
    assert metadata["workshop_cluster_ref"] == runtime["workshop_cluster_ref"] == "flightpath"
    assert metadata["onboarding_contract"] == (
        "catalog-onboarding/multi-agent-quickstart-flightpath.yaml"
    )
    assert metadata["certification_proof_contract"] == intake["certification"][
        "proof_contract"
    ]
    assert metadata["certification_stage"] == intake["certification"]["stage"]
    assert metadata["max_workshop_seats"] == intake["certification"][
        "max_workshop_seats"
    ]
    assert metadata["showroom_content_repo_url"] == intake["sources"]["showroom"][
        "repo_url"
    ]
    assert metadata["showroom_content_ref"] == intake["sources"]["showroom"][
        "revision"
    ]
    assert metadata["workload_repo"] == intake["sources"]["workload"]["repo_url"]
    assert metadata["workload_revision"] == intake["sources"]["workload"][
        "revision"
    ]
    assert metadata["showroom_tabs"] == runtime["tabs"]
