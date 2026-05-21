from __future__ import annotations

import json
import logging
import os
from typing import Optional

import requests

from app.domain.models import BrandingProfile

logger = logging.getLogger("launchpad.brand_generator")

BRAND_PROMPT = """Generate a branding profile for a company called "{company_name}".
{partner_context}

Return a JSON object with these exact fields:
- title: A professional platform title (e.g., "CompanyName AI Platform")
- primary_color: Hex color code for the primary brand color
- secondary_color: Hex color code for the secondary brand color
- theme: One of "default", "cockpit_dark", or "partner_light"
- footer_text: Short footer text for the platform

Return ONLY the JSON object, no explanation."""


class BrandGenerator:
    """Generates BrandingProfile from a company name using an LLM."""

    def __init__(
        self,
        llm_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        model: str = "granite-3-2-8b-instruct",
    ):
        self.llm_url = llm_url or os.environ.get("LITELLM_API_BASE", "")
        self.llm_api_key = llm_api_key or os.environ.get("LITELLM_API_KEY", "")
        self.model = model

    def generate(
        self,
        company_name: str,
        partner_type: Optional[str] = None,
    ) -> BrandingProfile:
        partner_context = ""
        if partner_type == "intel_internal":
            partner_context = "This is an Intel internal platform. Use Intel blue (#0068B5) as primary."
        elif partner_type == "redhat_internal":
            partner_context = "This is a Red Hat internal platform. Use Red Hat red (#EE0000) as primary."
        elif partner_type == "partner":
            partner_context = "This is a partner-facing platform. Use professional, neutral tones."

        try:
            resp = requests.post(
                f"{self.llm_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": BRAND_PROMPT.format(
                            company_name=company_name,
                            partner_context=partner_context,
                        )},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
                timeout=30,
            )

            if resp.status_code != 200:
                logger.warning("LLM returned %d, using defaults", resp.status_code)
                return self._default_profile(company_name)

            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            return BrandingProfile(
                branding_profile_id=f"ai-generated-{company_name.lower().replace(' ', '-')}",
                display_name=f"{company_name} Branding",
                title=data.get("title", f"{company_name} AI Platform"),
                primary_color=data.get("primary_color", "#EE0000"),
                secondary_color=data.get("secondary_color", "#0066CC"),
                footer_text=data.get("footer_text", f"Powered by {company_name}"),
                theme=data.get("theme", "default"),
            )
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON, using defaults")
            return self._default_profile(company_name)
        except Exception as e:
            logger.warning("Brand generation failed (%s), using defaults", e)
            return self._default_profile(company_name)

    def _default_profile(self, company_name: str) -> BrandingProfile:
        return BrandingProfile(
            branding_profile_id=f"default-{company_name.lower().replace(' ', '-')}",
            display_name=f"{company_name} Branding",
            title=f"{company_name} AI Platform",
            primary_color="#EE0000",
            secondary_color="#0066CC",
            footer_text=f"Powered by {company_name}",
        )
