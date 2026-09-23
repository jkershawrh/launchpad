from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "bootstrap-flightpath-candidate-maas.sh"


def test_bootstrap_is_idempotent_and_keeps_secrets_out_of_git() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "launchpad-litellm" in text
    assert "LITELLM_API_KEY" in text
    assert "DATABASE_URL" in text
    assert "openssl rand -hex" in text
    assert "--dry-run=client -o yaml" in text
    assert "oc apply -f -" in text
    assert "oc get secret" in text
    assert "ALTER ROLE litellm PASSWORD" in text
    assert "createdb" in text
    assert "rollout status deployment/launchpad-candidate-maas" in text

    assert 'echo "$candidate_maas_master_key"' not in text
    assert 'echo "$candidate_maas_db_password"' not in text
    assert "sk-flightpath-" not in text
