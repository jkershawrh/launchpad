"""LLM call audit logging — records model, tokens, latency for every inference call."""

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("launchpad.llm_audit")

_audit_log: list[dict] = []


def log_llm_call(
    model: str,
    prompt: str,
    output: str,
    latency_ms: float,
    trace_id: str = "",
    caller: str = "",
):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "caller": caller,
        "model": model,
        "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        "prompt_length": len(prompt),
        "output_length": len(output),
        "tokens_in_est": max(1, len(prompt.split())),
        "tokens_out_est": max(1, len(output.split())),
        "latency_ms": round(latency_ms, 1),
    }
    _audit_log.append(entry)
    if len(_audit_log) > 1000:
        _audit_log.pop(0)
    logger.info(
        "LLM call: model=%s caller=%s latency=%.0fms tokens_in=%d tokens_out=%d",
        model, caller, latency_ms, entry["tokens_in_est"], entry["tokens_out_est"],
    )
    return entry


def get_llm_audit_log() -> list[dict]:
    return list(_audit_log)


def audit_llm(func, model: str, caller: str, trace_id: str = ""):
    """Decorator-style wrapper for sync LLM calls."""
    def wrapper(prompt: str, *args, **kwargs) -> Any:
        start = time.time()
        result = func(prompt, *args, **kwargs)
        latency = (time.time() - start) * 1000
        output = str(result) if result else ""
        log_llm_call(model, prompt, output, latency, trace_id, caller)
        return result
    return wrapper
