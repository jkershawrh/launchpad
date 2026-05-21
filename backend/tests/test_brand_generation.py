"""
TDD: AI-powered brand generation.
Generates BrandingProfile from a company name using LLM.
"""
from unittest.mock import patch, MagicMock


class TestBrandGeneration:

    def test_brand_generator_importable(self):
        """RED: BrandGenerator should be importable."""
        from app.services.brand_generator import BrandGenerator
        gen = BrandGenerator()
        assert gen is not None

    def test_generate_brand_returns_profile(self):
        """RED: generate() should return a BrandingProfile."""
        from app.services.brand_generator import BrandGenerator
        from app.domain.models import BrandingProfile
        gen = BrandGenerator()

        with patch("app.services.brand_generator.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "choices": [{"message": {"content": '{"title": "Acme Corp AI Platform", "primary_color": "#FF5733", "secondary_color": "#2E86C1", "theme": "partner_light", "footer_text": "Powered by Acme Corp"}'}}]
                }),
            )
            profile = gen.generate("Acme Corp")
            assert isinstance(profile, BrandingProfile)
            assert profile.title == "Acme Corp AI Platform"
            assert profile.primary_color.startswith("#")

    def test_generate_brand_with_partner_type(self):
        """RED: should customize based on partner type."""
        from app.services.brand_generator import BrandGenerator
        gen = BrandGenerator()

        with patch("app.services.brand_generator.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "choices": [{"message": {"content": '{"title": "Intel AI Solutions", "primary_color": "#0068B5", "secondary_color": "#EE0000", "theme": "default", "footer_text": "Intel x Red Hat Partnership"}'}}]
                }),
            )
            profile = gen.generate("Intel", partner_type="intel_internal")
            assert "Intel" in profile.title

    def test_generate_brand_llm_failure_returns_default(self):
        """RED: LLM failure should return a sensible default."""
        from app.services.brand_generator import BrandGenerator
        gen = BrandGenerator()

        with patch("app.services.brand_generator.requests.post") as mock_post:
            mock_post.side_effect = Exception("LLM unavailable")
            profile = gen.generate("FailCorp")
            assert profile.title == "FailCorp AI Platform"
            assert profile.primary_color == "#EE0000"

    def test_generate_brand_bad_json_returns_default(self):
        """RED: malformed LLM response should return default."""
        from app.services.brand_generator import BrandGenerator
        gen = BrandGenerator()

        with patch("app.services.brand_generator.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "choices": [{"message": {"content": "not valid json"}}]
                }),
            )
            profile = gen.generate("BadJSON Corp")
            assert profile.title == "BadJSON Corp AI Platform"

    def test_generate_brand_api_endpoint(self):
        """RED: POST /api/branding-profiles/generate should work."""
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)

        with patch("app.services.brand_generator.requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={
                    "choices": [{"message": {"content": '{"title": "TestCo Platform", "primary_color": "#333333", "secondary_color": "#666666", "theme": "default", "footer_text": "TestCo"}'}}]
                }),
            )
            resp = client.post("/branding-profiles/generate", json={"company_name": "TestCo"})
            assert resp.status_code == 200
            assert "TestCo" in resp.json()["title"]
