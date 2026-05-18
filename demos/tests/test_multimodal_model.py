#!/usr/bin/env python3
"""Stage 1: Multimodal Request Model — TDD Red Phase"""

import sys
import pytest


@pytest.fixture(autouse=True)
def setup(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


class TestMultimodalFields:

    def test_modality_default_is_text(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="t1", task_type="classification", priority="normal", token_estimate=1000, latency_target_ms=5000)
        assert req.modality == "text"

    def test_modality_accepts_image(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="t2", task_type="image_classification", priority="normal", token_estimate=1000, latency_target_ms=5000, modality="image")
        assert req.modality == "image"

    def test_modality_accepts_screenshot(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="t3", task_type="screenshot_summary", priority="high", token_estimate=8000, latency_target_ms=5000, modality="screenshot")
        assert req.modality == "screenshot"

    def test_image_ref_default_empty(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="t4", task_type="classification", priority="normal", token_estimate=1000, latency_target_ms=5000)
        assert req.image_ref == ""

    def test_image_ref_accepts_path(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="t5", task_type="image_classification", priority="normal", token_estimate=1000, latency_target_ms=5000, image_ref="fixtures/multimodal/images/dashboard-001.json")
        assert "dashboard-001" in req.image_ref

    def test_document_ref_default_empty(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="t6", task_type="classification", priority="normal", token_estimate=1000, latency_target_ms=5000)
        assert req.document_ref == ""

    def test_image_count_default_zero(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="t7", task_type="classification", priority="normal", token_estimate=1000, latency_target_ms=5000)
        assert req.image_count == 0

    def test_page_count_default_zero(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="t8", task_type="classification", priority="normal", token_estimate=1000, latency_target_ms=5000)
        assert req.page_count == 0

    def test_multimodal_request_with_all_fields(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(
            request_id="mm-001", task_type="screenshot_summary", priority="high",
            token_estimate=18000, latency_target_ms=5000, modality="screenshot",
            image_ref="fixtures/multimodal/images/grafana-001.json", image_count=1, page_count=0,
            prompt="Summarize this dashboard screenshot.",
        )
        assert req.modality == "screenshot"
        assert req.image_count == 1
        assert req.page_count == 0
        assert "grafana" in req.image_ref

    def test_existing_text_request_unchanged(self):
        from overdrive.models import InferenceRequest
        req = InferenceRequest(request_id="text-001", task_type="classification", priority="normal", token_estimate=1000, latency_target_ms=8000, prompt="Classify this alert.")
        assert req.modality == "text"
        assert req.image_ref == ""
        assert req.document_ref == ""
        assert req.image_count == 0
        assert req.page_count == 0
