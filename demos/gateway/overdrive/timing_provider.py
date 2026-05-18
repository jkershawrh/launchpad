"""Timing providers for inference latency and throughput — mock and real."""

import os
import random
import time

LANE_BASE_LATENCY = {
    "eco": 80,
    "performance": 150,
    "overdrive": 200,
}

LANE_TOKENS_PER_SEC = {
    "eco": 30,
    "performance": 50,
    "overdrive": 120,
}


class MockTimingProvider:
    def __init__(self, seed: int = 42):
        self._seed = seed

    def simulate(
        self,
        lane: str,
        task_type: str,
        token_estimate: int,
        expected_output_tokens: int,
        modality: str = "text",
        image_count: int = 0,
        page_count: int = 0,
    ) -> dict:
        rng = random.Random(self._seed ^ hash((lane, task_type, token_estimate, expected_output_tokens)))

        base_latency = LANE_BASE_LATENCY.get(lane, 150)
        token_factor = token_estimate / 1000
        jitter = rng.uniform(0.8, 1.3)

        latency_ms = round(base_latency * (1 + token_factor * 0.1) * jitter, 1)

        image_overhead = image_count * rng.uniform(80, 200) if image_count > 0 else 0
        page_overhead = page_count * rng.uniform(150, 400) if page_count > 0 else 0
        latency_ms = round(latency_ms + image_overhead + page_overhead, 1)

        ttft_ms = round(latency_ms * rng.uniform(0.1, 0.3), 1)

        base_tps = LANE_TOKENS_PER_SEC.get(lane, 50)
        if modality != "text":
            base_tps = round(base_tps * 0.8, 1)
        output_tokens_per_sec = round(base_tps * rng.uniform(0.7, 1.4), 1)

        generation_time = (expected_output_tokens / output_tokens_per_sec * 1000) if output_tokens_per_sec > 0 else 0
        total_duration_ms = round(latency_ms + generation_time, 1)

        result = {
            "latency_ms": latency_ms,
            "ttft_ms": ttft_ms,
            "output_tokens_per_sec": output_tokens_per_sec,
            "total_duration_ms": total_duration_ms,
        }
        if image_count > 0:
            result["images_processed"] = image_count
        if page_count > 0:
            result["pages_processed"] = page_count
        return result


TASK_TO_LITELLM_MODEL = {
    "classification": "granite-4-0-h-tiny",
    "embedding": "nomic-embed-text-v1-5",
    "rerank": "codellama-7b-instruct",
    "short_summary": "codellama-7b-instruct",
    "long_summary": "llama-scout-17b",
    "incident_rca": "llama-scout-17b",
    "batch_summary": "llama-scout-17b",
    "rag_question": "llama-scout-17b",
    "document_summary": "llama-scout-17b",
    "code_summary": "llama-scout-17b",
    "image_classification": "granite-4-0-h-tiny",
    "screenshot_classification": "granite-4-0-h-tiny",
    "image_text_embedding": "nomic-embed-text-v1-5",
    "visual_similarity": "nomic-embed-text-v1-5",
    "ocr_layout_extract": "codellama-7b-instruct",
    "screenshot_summary": "llama-scout-17b",
    "chart_interpretation": "llama-scout-17b",
    "diagram_explanation": "llama-scout-17b",
    "document_visual_summary": "llama-scout-17b",
    "visual_rag_question": "llama-scout-17b",
    "multimodal_incident_summary": "llama-scout-17b",
    "multimodal_rca": "llama-scout-17b",
    "image_to_manual": "llama-scout-17b",
}


class RealTimingProvider:
    """Makes real inference calls through the gateway's /v1/route endpoint."""

    min_interval_ms = int(os.getenv("INFERENCE_THROTTLE_MS", "750"))

    def __init__(self, gateway_url: str = "http://localhost:8080", api_key: str = ""):
        self._gateway_url = gateway_url.rstrip("/")
        self._api_key = api_key
        self._last_call = 0.0

    def _throttle(self):
        now = time.monotonic()
        elapsed = (now - self._last_call) * 1000
        if elapsed < self.min_interval_ms:
            time.sleep((self.min_interval_ms - elapsed) / 1000)
        self._last_call = time.monotonic()

    def simulate(
        self,
        lane: str,
        task_type: str,
        token_estimate: int,
        expected_output_tokens: int,
        modality: str = "text",
        image_count: int = 0,
        page_count: int = 0,
    ) -> dict:
        import httpx

        self._throttle()

        model = TASK_TO_LITELLM_MODEL.get(task_type, "granite-4-0-h-tiny")
        task = task_type if task_type in ("classification", "embedding", "rerank") else "completion"

        payload = {
            "task": task,
            "model": model,
            "model_size_b": 17 if "scout" in model else 7 if "codellama" in model else 1,
            "prompt": f"[workload-demo] {task_type} benchmark request",
            "max_tokens": 60,
            "temperature": 0.3,
        }

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        start = time.monotonic()
        try:
            resp = httpx.post(
                f"{self._gateway_url}/v1/route",
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            latency_ms = round((time.monotonic() - start) * 1000, 1)

            if resp.status_code == 429:
                time.sleep(2)
                start2 = time.monotonic()
                resp = httpx.post(
                    f"{self._gateway_url}/v1/route",
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                latency_ms = round((time.monotonic() - start2) * 1000, 1)

            if resp.status_code != 200:
                return {
                    "latency_ms": latency_ms,
                    "ttft_ms": 0,
                    "output_tokens_per_sec": 0,
                    "total_duration_ms": latency_ms,
                    "error": f"HTTP {resp.status_code}",
                }

            data = resp.json()
            result = data.get("result", {}) or {}
            usage = result.get("usage", {}) or {}
            completion_tokens = usage.get("completion_tokens", expected_output_tokens)
            output_tps = round(completion_tokens / (latency_ms / 1000), 1) if latency_ms > 0 else 0

            return {
                "latency_ms": latency_ms,
                "ttft_ms": round(latency_ms * 0.2, 1),
                "output_tokens_per_sec": output_tps,
                "total_duration_ms": latency_ms,
            }

        except Exception as e:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "latency_ms": latency_ms,
                "ttft_ms": 0,
                "output_tokens_per_sec": 0,
                "total_duration_ms": latency_ms,
                "error": str(e),
            }
