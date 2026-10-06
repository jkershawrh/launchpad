import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/browser_access_certification_preflight.py"
SPEC = importlib.util.spec_from_file_location("browser_access_preflight", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
evaluate = MODULE.evaluate
evaluate_source = MODULE.evaluate_source


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def _healthy_opener(request, **_kwargs):
    assert request.full_url.startswith("https://labs.smg-helix.ai/")
    assert request.get_header("User-agent") == (
        "launchpad-browser-certification-preflight/1"
    )
    return _Response()


def test_source_preflight_covers_every_active_catalog() -> None:
    result = evaluate_source(ROOT)

    assert result["passed"] is True
    assert result["active_catalog_count"] == 23
    assert result["profile_count"] == 9
    assert result["unassigned_catalogs"] == []
    assert result["unknown_catalogs"] == []


def test_preflight_is_read_only_and_keeps_live_seat_proof_open() -> None:
    result = evaluate(ROOT, opener=_healthy_opener)

    assert result["passed"] is True
    assert result["mutates_cluster"] is False
    assert result["public_edge"]["passed"] is True
    assert result["live_seat_proof"] == "not_run"


def test_source_only_mode_does_not_claim_public_edge_proof() -> None:
    result = evaluate(ROOT, network=False)

    assert result["passed"] is True
    assert result["public_edge"] == {"passed": None, "status": "not_run"}
