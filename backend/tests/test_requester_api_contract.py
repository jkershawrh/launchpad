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


def test_request_and_workshop_reads_use_secret_free_response_models():
    schema = app.openapi()

    assert _response_schema("/api/v1/lab-requests", "post", "201") == {
        "$ref": "#/components/schemas/LabRequestCreateResponse"
    }
    assert _response_schema("/api/v1/lab-requests/{request_id}", "get", "200") == {
        "$ref": "#/components/schemas/LabRequestResponse"
    }
    assert _response_schema("/api/v1/workshops/{workshop_id}", "get", "200") == {
        "$ref": "#/components/schemas/WorkshopResponse"
    }
    assert schema["components"]["schemas"]["LabRequestCreateResponse"]["properties"][
        "one_time_access_code"
    ]["readOnly"] is True
    for method, path, status in (
        ("post", "/api/v1/workshops", "201"),
        ("post", "/api/v1/workshops/{workshop_id}/confirm", "202"),
        ("post", "/api/v1/workshops/{workshop_id}/retry-failed", "202"),
        ("delete", "/api/v1/workshops/{workshop_id}", "202"),
    ):
        assert _response_schema(path, method, status) == {
            "$ref": "#/components/schemas/WorkshopResponse"
        }
