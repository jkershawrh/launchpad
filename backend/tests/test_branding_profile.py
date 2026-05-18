import pytest
from pydantic import ValidationError

from app.domain.enums import BrandingTheme
from app.domain.models import BrandingProfile


def test_branding_profile_applies_title_and_colors():
    bp = BrandingProfile(
        branding_profile_id="partner-oem-a",
        display_name="Partner OEM A",
        title="Partner OEM A AI Lab",
        primary_color="#1A1A2E",
        secondary_color="#0071C5",
        footer_text="Partner OEM A — Powered by Intel and Red Hat",
        theme=BrandingTheme.PARTNER_LIGHT,
    )
    assert bp.title == "Partner OEM A AI Lab"
    assert bp.primary_color == "#1A1A2E"
    assert bp.secondary_color == "#0071C5"
    assert bp.theme == BrandingTheme.PARTNER_LIGHT
    assert bp.footer_text == "Partner OEM A — Powered by Intel and Red Hat"


def test_branding_profile_defaults():
    bp = BrandingProfile(
        branding_profile_id="default",
        display_name="Default",
        title="Partner AI Launchpad",
    )
    assert bp.primary_color == "#EE0000"
    assert bp.secondary_color == "#0066CC"
    assert bp.theme == BrandingTheme.DEFAULT
    assert bp.logo_refs == []


def test_branding_profile_rejects_empty_id():
    with pytest.raises(ValidationError):
        BrandingProfile(
            branding_profile_id="",
            display_name="Bad",
            title="Bad",
        )
