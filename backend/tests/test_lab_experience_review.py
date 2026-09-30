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

    assert lab["overall_status"] == "immutable-source-published-draft"
    assert catalog["status"] == intake["catalog"]["status"] == "draft"
    assert catalog["metadata"]["certification_stage"] == (
        intake["certification"]["stage"]
    ) == "immutable-source-published"
    assert intake["certification"]["certified_seats"] == 0
    assert intake["sources"]["workload"]["revision"] == (
        "c4c5a20792f361c360d64a3d997e8ec19c0f7781"
    )
    values = intake["runtime"]["workload"]["helm_values"]
    assert values["adapter"]["mode"] == "live"
    assert values["adapter"]["policy"]["approvedModels"] == (
        "granite-3.2-8b-tools"
    )
    assertions = contract["spec"]["seat_probe"]["json_assertions"]
    assert {"path": "journey.mode", "equals": "LIVE"} in assertions
    assert {"path": "journey.model_participated", "equals": True} in assertions
    assert {"path": "journey.model", "equals": "granite-3.2-8b-tools"} in assertions


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

    assert lab["overall_status"] == "immutable-source-published-draft"
    assert catalog["status"] == intake["catalog"]["status"] == "draft"
    assert catalog["metadata"]["certification_stage"] == (
        intake["certification"]["stage"]
    ) == "immutable-source-published"
    assert intake["certification"]["max_workshop_seats"] == 1
    assert intake["references"]["original_lab"]["revision"] == (
        "ea61ce4e20f6e12513b16eeaa746f81895e716c9"
    )
    values = intake["runtime"]["workload"]["helm_values"]
    assert values["image"] == {
        "repository": "ghcr.io/jkershawrh/multi-agent-quickstart",
        "digest": "sha256:a772cd2979a1cc21d19273359b611be8e6848cedb3cb9ce478d5f963eec7cbbd",
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
            "revision": "b8274c70cde28246a2c9bba0ba689a4dc57088b9",
            "presentation": "sha256:9c8b67c94f7bc62ec460b8a9ad18b42c65c8e8b6defc49a6c62092ca14921f11",
            "workload": "sha256:773d0f7c9c594d54a801d773cce752c01635155829e043783416b3405e182bd1",
        },
        "virtualization-ai-401": {
            "revision": "529281616de3f11a2b5355314cd4f7123935e02d",
            "presentation": "sha256:eaf0ccb49b88c879ea6d7e36fbdf44cf9a3c1abc3685af871c5d856efcc8087a",
            "workload": "sha256:ebfc3c0dfa95efe49b1cb8b59bf5e8445f502a6583996c777fee4d8132d197ca",
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

        assert catalog["status"] == intake["catalog"]["status"] == "draft"
        assert metadata["certification_stage"] == (
            intake["certification"]["stage"]
        ) == "immutable-source-published"
        assert metadata["workload_revision"] == release["revision"]
        assert metadata["showroom_content_ref"] == release["revision"]
        assert intake["sources"]["workload"]["revision"] == release["revision"]
        assert intake["sources"]["showroom"]["revision"] == release["revision"]
        assert release["presentation"] in str(metadata["workload_helm_values"])
        assert release["workload"] in str(metadata["workload_helm_values"])
        assert review["labs"][catalog_id]["overall_status"] == (
            "immutable-source-published-draft"
        )

    virtualization_401 = review["labs"]["virtualization-ai-401"]["source_state"]
    assert virtualization_401["published_revision"] == (
        "529281616de3f11a2b5355314cd4f7123935e02d"
    )
    assert virtualization_401["catalog_pinned_revision"] == (
        "529281616de3f11a2b5355314cd4f7123935e02d"
    )
    assert virtualization_401["publication_workflow"] == (
        "https://github.com/jkershawrh/virtualization-ai-401/actions/runs/36743086189"
    )
    assert virtualization_401["immutable_images"] == {
        "presentation": "ghcr.io/jkershawrh/virtualization-ai-401-presentation@sha256:eaf0ccb49b88c879ea6d7e36fbdf44cf9a3c1abc3685af871c5d856efcc8087a",
        "operations_adapter": "ghcr.io/jkershawrh/virtualization-ai-401-operations-adapter@sha256:ebfc3c0dfa95efe49b1cb8b59bf5e8445f502a6583996c777fee4d8132d197ca",
    }


def test_virtualization_401_certification_capabilities_match_flightpath() -> None:
    catalog = yaml.safe_load(
        (ROOT / "catalog/virtualization-ai-401/catalog-item.yaml").read_text()
    )
    intake = yaml.safe_load(
        (ROOT / "catalog-onboarding/virtualization-ai-401.yaml").read_text()
    )
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


def test_applied_lab_reviews_separate_live_proof_from_local_source_updates() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    expected_states = {
        "network-operations-agent": {
            "revision": "6ed5c53337afa55c03949b2963b429f32977ef69",
            "overall": "immutable-source-published-draft",
            "cleanup": "green-local",
            "change_state": "committed-published-pinned-not-live-certified",
        },
        "hybrid-fraud-detection": {
            "revision": "9dccae859e939d836c06cc9fb51d8ae4a848a38f",
            "overall": "immutable-source-published-draft",
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


def test_sovereign_101_records_the_exact_published_candidate_without_inheriting_live_proof() -> None:
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    lab = review["labs"]["sovereign-ai-101"]
    release = lab["release"]

    assert lab["overall_status"] == "immutable-source-published-draft"
    assert lab["candidate_revision"] == (
        "a23ed5c03a8ae4f68ad819bbc8ae1b6a9d62a767"
    )
    assert release["status"] == "published-not-live-certified"
    assert release["workflow"].endswith("/actions/runs/36731862663")
    assert release["presentation_image"].endswith(
        "@sha256:be49d6e3b295c784aefaa416f5ac86a02b30aca3c164baa4d4c0acd25d563e49"
    )
    assert release["rehearsal_image"].endswith(
        "@sha256:a38b17cca8ff0cea22bdd4d447503b20afd454b33f3d8a714b1ec39582420351"
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


def test_virtualization_foundations_is_not_orderable_until_vm_origin_is_proven() -> None:
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

    assert catalog["status"] == "draft"
    assert catalog["metadata"]["certification_stage"] == "source-reviewed"
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
    assert (
        "fresh-one-seat-vm-origin-console-model-and-reclaim-certification"
        in catalog["metadata"]["activation_blockers"]
    )
    assert intake["catalog"]["status"] == "draft"
    assert intake["certification"]["certified_seats"] == 0
    assert catalog["metadata"]["showroom_content_ref"] == intake["sources"][
        "showroom"
    ]["revision"] == "df4dbea9b746f9e65b4c611f96e7e76b4a2cafb6"
    assert catalog["metadata"]["showroom_content_image"] == intake["sources"][
        "showroom"
    ]["content_image"]
    assert catalog["metadata"]["workload_helm_values"] == intake["runtime"][
        "workload"
    ]["helm_values"]

    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))["labs"][
        "virtualization-ai-foundations-101"
    ]
    assert review["overall_status"] == (
        "immutable-source-published-draft-live-certification-required"
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
