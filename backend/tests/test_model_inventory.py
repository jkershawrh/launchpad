from unittest.mock import MagicMock, patch

from app.services.model_inventory import get_model_inventory


PORTFOLIO = [
    {"id": "smollm3", "display_name": "SmolLM3 3B", "namespace": "intel-inference", "workload": "llama-smollm3-3b"},
    {"id": "phi4-mini", "display_name": "Phi-4 Mini", "namespace": "intel-inference", "workload": "llama-phi4-mini"},
]


@patch("app.services.model_inventory.httpx.get")
@patch("app.services.model_inventory._apps_api")
def test_inventory_distinguishes_running_exposed_and_stopped(apps_api, http_get):
    running = MagicMock()
    running.spec.replicas = 1
    running.status.ready_replicas = 1
    stopped = MagicMock()
    stopped.spec.replicas = 0
    stopped.status.ready_replicas = None
    apps_api.return_value.read_namespaced_deployment.side_effect = [running, stopped]
    http_get.return_value.raise_for_status.return_value = None
    http_get.return_value.json.return_value = {"data": [{"id": "smollm3"}]}

    result = get_model_inventory(PORTFOLIO, "http://litellm", "secret")

    assert result["summary"] == {"configured": 2, "running": 1, "exposed": 1, "healthy": 1}
    assert result["models"][0]["status"] == "healthy"
    assert result["models"][0]["litellm_exposed"] is True
    assert result["models"][1]["status"] == "stopped"


@patch("app.services.model_inventory.httpx.get")
@patch("app.services.model_inventory._apps_api")
def test_running_model_not_exposed_is_reported_accurately(apps_api, http_get):
    workload = MagicMock()
    workload.spec.replicas = 1
    workload.status.ready_replicas = 1
    apps_api.return_value.read_namespaced_deployment.return_value = workload
    http_get.return_value.raise_for_status.return_value = None
    http_get.return_value.json.return_value = {"data": []}

    result = get_model_inventory(PORTFOLIO[:1], "http://litellm")

    assert result["models"][0]["status"] == "running_not_exposed"
    assert result["summary"]["healthy"] == 0
