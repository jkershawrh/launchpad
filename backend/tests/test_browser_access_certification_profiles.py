from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "certification/browser-access-profiles-v1.yaml"
PUBLIC_EXPOSURE_CONTRACT = ROOT / "contracts/public-exposure-certification-v1.yaml"


def _active_catalogs() -> set[str]:
    active = set()
    for path in (ROOT / "catalog").glob("*/catalog-item.yaml"):
        item = yaml.safe_load(path.read_text(encoding="utf-8"))
        if item.get("status") == "active":
            active.add(item["catalog_item_id"])
    return active


def test_every_active_catalog_has_exactly_one_browser_profile() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    profiles = contract["spec"]["profiles"]
    assigned = [catalog for profile in profiles.values() for catalog in profile["catalogs"]]

    assert len(assigned) == len(set(assigned))
    assert set(assigned) == _active_catalogs()


def test_each_profile_representative_is_a_member_and_active() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    active = _active_catalogs()

    for profile in contract["spec"]["profiles"].values():
        assert profile["representative"] in profile["catalogs"]
        assert profile["representative"] in active
        assert profile["additional_gates"]


def test_single_origin_gate_preserves_full_security_and_cleanup_proof() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    spec = contract["spec"]

    assert contract["metadata"]["public_origin"] == "https://labs.smg-helix.ai"
    assert {
        "trusted_tls_without_browser_bypass",
        "openshift_console_sso",
        "assigned_namespace_edit",
        "cross_namespace_denied",
        "cluster_scoped_access_denied",
        "no_recursive_iframe",
        "reclaim_is_idempotent",
        "zero_residue",
    } <= set(spec["shared_gates"])
    assert spec["change_classes"]["edge_only"]["workload_recertification"] is False
    assert spec["change_classes"]["tab_contract"]["required_proof"] == [
        "fresh_one_seat_full_browser_journey_for_each_affected_catalog"
    ]
    assert spec["change_classes"]["runtime"]["workload_recertification"] is True
    assert spec["change_classes"]["scale"]["required_proof"][-1] == (
        "twenty_five_seat_certification_before_advertising_twenty_five"
    )


def test_public_exposure_contract_uses_the_profile_matrix_and_change_boundaries() -> None:
    contract = yaml.safe_load(PUBLIC_EXPOSURE_CONTRACT.read_text(encoding="utf-8"))
    spec = contract["spec"]

    assert spec["browserAccessProfiles"] == (
        "certification/browser-access-profiles-v1.yaml"
    )
    recertification = spec["recertification"]
    assert recertification["edgeOnly"] == {
        "fullRepresentativeSeatPerBrowserProfile": True,
        "browserSmokePerActiveCatalog": True,
        "repeatUnchangedRuntimeProbe": False,
    }
    assert recertification["contentOnly"]["liveSeatRequired"] is False
    assert recertification["tabContract"]["freshAffectedCatalogSeatRequired"] is True
    assert recertification["runtime"]["completeLabAndLifecycleSeatRequired"] is True
