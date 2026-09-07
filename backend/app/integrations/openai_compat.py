from __future__ import annotations


def openai_api_url(api_base: str, path: str) -> str:
    """Build an OpenAI-compatible URL whether the configured base has /v1."""
    base = api_base.rstrip("/")
    versioned_base = base if base.endswith("/v1") else f"{base}/v1"
    return f"{versioned_base}/{path.lstrip('/')}"
