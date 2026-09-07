"""CDD contract for the requester workshop API consumed by the React portal."""

from app.main import app


def _response_schema(path: str, method: str, status: str) -> dict:
    return app.openapi()["paths"][path][method]["responses"][status]["content"]["application/json"][
        "schema"
    ]


def test_capacity_preview_has_a_versioned_typed_response_contract():
    schema = app.openapi()

    assert _response_schema("/api/v1/workshops/capacity-preview", "post", "200") == {
        "$ref": "#/components/schemas/WorkshopCapacityPreview"
    }
    preview = schema["components"]["schemas"]["WorkshopCapacityPreview"]
    assert {
        "can_provision",
        "reason",
        "seats_requested",
        "estimated_resources",
    }.issubset(set(preview["required"]))
    resources_ref = preview["properties"]["estimated_resources"]["$ref"]
    resources = schema["components"]["schemas"][resources_ref.rsplit("/", 1)[-1]]
    assert set(resources["required"]) == {
        "cpu_millicores",
        "memory_mib",
        "pods",
    }


def test_workshop_order_response_explicitly_models_one_time_secret():
    schema = app.openapi()

    assert _response_schema("/api/v1/workshops/orders", "post", "201") == {
        "$ref": "#/components/schemas/WorkshopOrderResponse"
    }
    response = schema["components"]["schemas"]["WorkshopOrderResponse"]
    assert response["properties"]["one_time_access_code"]["readOnly"] is True
