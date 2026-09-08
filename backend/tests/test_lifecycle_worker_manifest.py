from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "deploy/launchpad/base"


def test_lifecycle_worker_is_shipped_disabled_until_ha_certification() -> None:
    kustomization = yaml.safe_load((BASE / "kustomization.yaml").read_text())
    assert "lifecycle-worker-deployment.yaml" in kustomization["resources"]

    deployment = yaml.safe_load(
        (BASE / "lifecycle-worker-deployment.yaml").read_text()
    )
    assert deployment["metadata"]["name"] == "lifecycle-worker"
    assert deployment["spec"]["replicas"] == 0
    assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == (
        "launchpad-backend"
    )
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["command"] == ["python", "-m", "app.lifecycle_worker_main"]
    assert container["env"][0]["name"] == "DATABASE_URL"


def test_lifecycle_scheduler_only_enqueues_durable_system_jobs() -> None:
    kustomization = yaml.safe_load((BASE / "kustomization.yaml").read_text())
    assert "lifecycle-scheduler-cronjob.yaml" in kustomization["resources"]

    cronjob = yaml.safe_load(
        (BASE / "lifecycle-scheduler-cronjob.yaml").read_text()
    )
    assert cronjob["kind"] == "CronJob"
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    container = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"][
        "containers"
    ][0]
    assert container["command"] == [
        "python",
        "-m",
        "app.lifecycle_scheduler_main",
    ]


def test_lifecycle_ha_feature_flag_defaults_off() -> None:
    config = yaml.safe_load((BASE / "configmap.yaml").read_text())

    assert config["data"]["LIFECYCLE_HA_ENABLED"] == "false"
    assert config["data"]["LAUNCHPAD_CONTROL_PLANE_ROLE"] == "active"
    assert config["data"]["LIFECYCLE_JOB_LEASE_SECONDS"] == "120"
    assert config["data"]["LIFECYCLE_HEARTBEAT_INTERVAL_SECONDS"] == "15"
