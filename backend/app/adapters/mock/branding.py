from __future__ import annotations

from typing import Dict, List, Optional

from app.domain.enums import BrandingTheme
from app.domain.models import BrandingProfile

SEED_PROFILES = [
    {
        "branding_profile_id": "redhat-intel-default",
        "display_name": "Red Hat + Intel Default",
        "title": "Partner AI Launchpad",
        "logo_refs": ["/logos/redhat.png", "/logos/intel.png"],
        "primary_color": "#EE0000",
        "secondary_color": "#0071C5",
        "footer_text": "Powered by Red Hat OpenShift and Intel",
        "theme": BrandingTheme.DEFAULT,
    },
    {
        "branding_profile_id": "intel-internal",
        "display_name": "Intel",
        "title": "Intel AI Lab Platform",
        "logo_refs": ["/logos/intel.png", "/logos/redhat.png"],
        "primary_color": "#0071C5",
        "secondary_color": "#00C7FD",
        "footer_text": "Intel AI — Powered by Red Hat OpenShift",
        "theme": BrandingTheme.DEFAULT,
        "metadata": {
            "accent_color": "#0071C5",
            "header_bg": "#0A1628",
            "font_family": "Intel One Display, system-ui, sans-serif",
        },
    },
    {
        "branding_profile_id": "partner-oem-a",
        "display_name": "Partner OEM A",
        "title": "Partner OEM A AI Lab",
        "logo_refs": ["/logos/redhat.png", "/logos/intel.png"],
        "primary_color": "#1A1A2E",
        "secondary_color": "#0071C5",
        "footer_text": "Partner OEM A — Powered by Intel and Red Hat",
        "theme": BrandingTheme.PARTNER_LIGHT,
    },
]


class FileBrandingAdapter:
    def __init__(self) -> None:
        self._profiles: Dict[str, BrandingProfile] = {}
        for data in SEED_PROFILES:
            profile = BrandingProfile(**data)
            self._profiles[profile.branding_profile_id] = profile

    def load_profile(self, branding_profile_id: str) -> Optional[BrandingProfile]:
        return self._profiles.get(branding_profile_id)

    def list_profiles(self) -> List[BrandingProfile]:
        return list(self._profiles.values())
