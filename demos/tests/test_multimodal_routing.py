#!/usr/bin/env python3
"""Stage 2: Multimodal Routing Matrix — TDD Red Phase"""

import sys
import pytest


@pytest.fixture(autouse=True)
def setup(project_root):
    p = str(project_root / "gateway")
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def config(project_root):
    from overdrive.matrix import load_config
    return load_config(project_root / "gateway" / "overdrive" / "config.yaml")


class TestMultimodalRouting:

    def test_image_classification_to_eco(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("image_classification", 1000, "normal", 8000, config) == "eco"

    def test_screenshot_classification_to_eco(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("screenshot_classification", 1000, "normal", 8000, config) == "eco"

    def test_image_text_embedding_to_performance(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("image_text_embedding", 4000, "normal", 5000, config) == "performance"

    def test_visual_similarity_to_performance(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("visual_similarity", 4000, "normal", 5000, config) == "performance"

    def test_ocr_layout_extract_to_performance(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("ocr_layout_extract", 6000, "normal", 5000, config) == "performance"

    def test_screenshot_summary_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("screenshot_summary", 10000, "high", 5000, config) == "overdrive"

    def test_chart_interpretation_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("chart_interpretation", 10000, "high", 5000, config) == "overdrive"

    def test_diagram_explanation_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("diagram_explanation", 10000, "high", 5000, config) == "overdrive"

    def test_document_visual_summary_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("document_visual_summary", 20000, "high", 5000, config) == "overdrive"

    def test_visual_rag_question_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("visual_rag_question", 16000, "high", 5000, config) == "overdrive"

    def test_multimodal_incident_summary_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("multimodal_incident_summary", 20000, "critical", 5000, config) == "overdrive"

    def test_multimodal_rca_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("multimodal_rca", 25000, "critical", 5000, config) == "overdrive"


class TestMultimodalCapabilities:

    def test_eco_has_image_classification(self, config):
        assert "image_classification" in config["lanes"]["eco"]["capabilities"]

    def test_eco_has_screenshot_classification(self, config):
        assert "screenshot_classification" in config["lanes"]["eco"]["capabilities"]

    def test_performance_has_image_text_embedding(self, config):
        assert "image_text_embedding" in config["lanes"]["performance"]["capabilities"]

    def test_performance_has_visual_similarity(self, config):
        assert "visual_similarity" in config["lanes"]["performance"]["capabilities"]

    def test_overdrive_has_screenshot_summary(self, config):
        assert "screenshot_summary" in config["lanes"]["overdrive"]["capabilities"]

    def test_overdrive_has_multimodal_rca(self, config):
        assert "multimodal_rca" in config["lanes"]["overdrive"]["capabilities"]


class TestExistingTextRoutingRegression:

    def test_classification_still_routes_to_eco(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("classification", 1000, "normal", 8000, config) == "eco"

    def test_embedding_still_routes_to_performance(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("embedding", 4000, "normal", 5000, config) == "performance"

    def test_long_summary_still_routes_to_overdrive(self, config):
        from overdrive.matrix import match_lane
        assert match_lane("long_summary", 20000, "high", 5000, config) == "overdrive"
