from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_virtualization_probe_emits_only_the_result_json_on_stdout() -> None:
    probe = (
        REPO_ROOT / "scripts" / "certify-virtualization-ai-seat.sh"
    ).read_text()

    wait_lines = [line.strip() for line in probe.splitlines() if " wait " in line]

    assert wait_lines
    assert all(line.endswith(">/dev/null") for line in wait_lines)
