import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "evidence/runs/arena-lifecycle-5-seat-cross-node-workshop-ha-20260909T020155Z.json"
)
CHECKSUM = Path(f"{EVIDENCE}.sha256")


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text())


def test_five_seat_workshop_ha_receipt_is_hashed_and_green_live():
    evidence = _evidence()
    expected_hash = CHECKSUM.read_text().split()[0]

    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == expected_hash
    assert evidence["schema"] == (
        "launchpad.redhat.com/workshop-lifecycle-ha-live-certification/v1"
    )
    assert evidence["result"] == "GREEN-live-five-seat-cross-node-workshop-ha"
    assert evidence["source"]["commit"] == (
        "90413c95682f898c362f512a8f7acd66efb4fa6e"
    )
    assert evidence["source"]["backend_image"].endswith(
        "@sha256:90790c6ae143f862e0d0e2c73c69ede394ce71cf97cc68c0b86905c03745ccbf"
    )


def test_five_seat_workshop_ha_proves_every_unique_participant_environment():
    workshop = _evidence()["workshop"]
    seats = workshop["seat_proofs"]

    assert workshop["cluster_ref"] == "arena"
    assert workshop["seats_requested"] == 5
    assert workshop["seats_ready"] == 5
    assert workshop["unique_session_ids"] == 5
    assert workshop["unique_namespaces"] == 5
    assert [seat["seat_number"] for seat in seats] == [1, 2, 3, 4, 5]
    assert len({seat["session_id"] for seat in seats}) == 5
    assert len({seat["namespace"] for seat in seats}) == 5
    assert all(seat["status"] == "ready" for seat in seats)
    assert all(seat["showroom_http"] == 200 for seat in seats)


def test_five_seat_workshop_ha_proves_fenced_takeover_and_zero_residue():
    evidence = _evidence()
    provision = evidence["provision_takeover"]
    reclaim = evidence["reclaim_takeover"]

    assert provision["initial"]["fencing_token"] == 1
    assert provision["takeover"]["final"]["fencing_token"] == 2
    assert provision["takeover"]["takeover_seconds"] < 60
    assert provision["takeover"]["completion_seconds"] < 600
    assert reclaim["initial"]["fencing_token"] == 3
    assert reclaim["takeover"]["final"]["fencing_token"] == 4
    assert reclaim["takeover"]["takeover_seconds"] < 60
    assert reclaim["takeover"]["completion_seconds"] < 120
    assert provision["takeover"]["replacement_owner"] != provision["initial"]["owner_id"]
    assert reclaim["takeover"]["replacement_owner"] != reclaim["initial"]["owner_id"]
    assert set(evidence["topology"]["worker_nodes"]) == {
        "gnr2.fm2aihpcsed.com",
        "rhgnr1",
    }
    assert evidence["cleanup"] == {
        "namespaces": 0,
        "routes": 0,
        "role_bindings": 0,
        "argocd_applications": 0,
    }


def test_five_seat_workshop_ha_preserves_security_and_release_boundary():
    evidence = _evidence()

    assert evidence["public_certification_lab_preserved"] is True
    assert evidence["security"] == {
        "contains_plaintext_credentials": False,
        "credential_values_logged": False,
    }
    assert evidence["certification_boundary"] == {
        "five_seat_workshop_process_ha": "certified",
        "twenty_five_seat_workshop_ha": "not certified",
        "hard_node_failure": "not certified",
        "flightpath_dr": "not certified",
    }
