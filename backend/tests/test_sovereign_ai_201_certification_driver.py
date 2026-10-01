from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_sovereign_201_driver_waits_for_the_live_model_path() -> None:
    driver = (ROOT / "scripts/certify-sovereign-ai-201-seat.sh").read_text()

    assert "--max-time 75" in driver
    assert "for attempt in {1..4}" in driver
    assert 'candidate="$(request_json 200 POST' in driver
    assert "model_participated == true" in driver
    assert 'allowed="$candidate"' in driver
    assert '[[ -n "$allowed" ]]' in driver
