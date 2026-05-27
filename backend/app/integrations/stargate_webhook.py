"""Backward-compatibility shim — delegates to event_publisher."""
# Re-export everything so existing imports keep working.
from app.integrations.event_publisher import (  # noqa: F401
    STARGATE_API_URL,
    STARGATE_API_KEY,
    STARGATE_SSL_VERIFY,
    notify_stargate,
    publish_event,
    _push,
)

# Allow tests to patch urllib at the old module path
import urllib.request  # noqa: F401
