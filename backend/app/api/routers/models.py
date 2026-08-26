from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.auth.oauth import get_current_user
from app.api.deps import provisioning_service
from app.services.model_inventory import get_model_inventory


router = APIRouter(
    prefix="/models",
    tags=["models"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def available_models() -> Dict[str, Any]:
    """Return models that are ready and exposed for new environment requests."""
    inventory = get_model_inventory()
    registry = provisioning_service.cluster_registry
    configured = (
        {
            model_id
            for target in registry.list_enabled()
            for model_id in target.model_endpoints
        }
        if registry else set()
    )
    fields = ("id", "display_name", "hardware", "use_case", "status")
    return {
        "models": [
            {field: model[field] for field in fields}
            for model in inventory.get("models", [])
            if model.get("status") == "healthy"
            and (not configured or model.get("id") in configured)
        ]
    }
