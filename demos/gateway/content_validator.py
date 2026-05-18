"""Content Validation — security scanning for partner-submitted artifacts."""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)

BLOCKED_PATTERNS = [
    r"\.\./",
    r"/etc/",
    r"/proc/",
    r"\.env$",
    r"credentials",
    r"\.pem$",
    r"\.key$",
    r"__pycache__",
    r"\.pyc$",
]

WARNING_PATTERNS = [
    r"\.bin$",
    r"\.pkl$",
    r"\.pt$",
    r"eval\(",
    r"exec\(",
    r"import os",
    r"subprocess",
]

ALLOWED_TYPES = {"model", "dataset", "config", "image", "document"}
MAX_NAME_LENGTH = 200


def validate_artifact(artifact: dict) -> dict:
    name = artifact.get("name", "")
    artifact_type = artifact.get("type", "unknown")
    source = artifact.get("source", "unknown")

    checks: List[dict] = []
    status = "passed"

    if not name or len(name) > MAX_NAME_LENGTH:
        checks.append({"check": "name_length", "result": "blocked", "detail": "Name missing or too long"})
        status = "blocked"

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            checks.append({"check": "path_traversal", "result": "blocked", "detail": f"Blocked pattern: {pattern}"})
            status = "blocked"

    if artifact_type not in ALLOWED_TYPES:
        checks.append({"check": "type_validation", "result": "warning", "detail": f"Unknown artifact type: {artifact_type}"})
        if status == "passed":
            status = "warning"

    for pattern in WARNING_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            checks.append({"check": "suspicious_extension", "result": "warning", "detail": f"Suspicious pattern: {pattern}"})
            if status == "passed":
                status = "warning"

    if source not in ("internal", "partner", "verified"):
        checks.append({"check": "source_verification", "result": "warning", "detail": f"Unverified source: {source}"})
        if status == "passed":
            status = "warning"

    if not checks:
        checks.append({"check": "all_clear", "result": "passed", "detail": "No issues found"})

    return {
        "status": status,
        "artifact_name": name,
        "artifact_type": artifact_type,
        "source": source,
        "checks": checks,
        "total_checks": len(checks),
    }
