#!/usr/bin/env python3
"""
vLLM Gaudi Inference Server - V1 (Local Testing)

V1: Mock mode for local testing without Gaudi hardware
V2: Real Gaudi HPU backend when deployed to cluster

OpenAI-compatible API endpoints:
- GET  /health         - Health check
- GET  /v1/models      - List available models
- POST /v1/completions - Text completion
"""

import os
import sys
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
import uvicorn

# Check if running in mock mode (V1) or real Gaudi mode (V2)
USE_MOCK_GAUDI = os.getenv("HABANA_USE_MOCK", "false").lower() == "true"

try:
    import habana_frameworks.torch as ht
    import habana_frameworks.torch.core as htcore
    GAUDI_AVAILABLE = True
except ImportError:
    GAUDI_AVAILABLE = False

# Import PyTorch and transformers
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global model and tokenizer
model = None
tokenizer = None
model_name = os.getenv("MODEL_NAME", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")

# API key authentication
API_KEY = os.getenv("API_KEY", "")


async def verify_api_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# Request/Response models
class CompletionRequest(BaseModel):
    model: str
    prompt: str
    max_tokens: int = Field(default=16, ge=1, le=2048)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    n: int = Field(default=1, ge=1, le=10)
    stream: bool = False
    stop: Optional[List[str]] = None


class CompletionChoice(BaseModel):
    text: str
    index: int
    finish_reason: str


class CompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class CompletionResponse(BaseModel):
    id: str
    object: str = "text_completion"
    created: int
    model: str
    choices: List[CompletionChoice]
    usage: CompletionUsage


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "huggingface"


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


def detect_device():
    """Detect available compute device"""
    if USE_MOCK_GAUDI:
        logger.info("Running in MOCK GAUDI mode (V1 - local testing)")
        return "cpu"

    if GAUDI_AVAILABLE:
        try:
            if torch.hpu.is_available():
                logger.info("Detected Gaudi HPU device")
                return "hpu"
        except Exception as e:
            logger.warning(f"Gaudi detection failed: {e}")

    logger.info("Using CPU device")
    return "cpu"


def load_model():
    """Load model and tokenizer"""
    global model, tokenizer

    device = detect_device()

    logger.info(f"Loading model: {model_name}")
    logger.info(f"Target device: {device}")

    try:
        # Load tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name)

        # Ensure tokenizer has pad token
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # Load model
        logger.info("Loading model weights...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16 if device == "hpu" else torch.float32,
            low_cpu_mem_usage=True
        )

        model = model.to(device)
        if device == "hpu":
            htcore.mark_step()

        model.eval()

        logger.info(f"Model loaded successfully on {device}")
        logger.info(f"Model device: {next(model.parameters()).device}")

        return True

    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise


@asynccontextmanager
async def lifespan(app):
    """Initialize model on startup, cleanup on shutdown"""
    logger.info("Starting vLLM Gaudi Inference Server V1")
    logger.info(f"Mock mode: {USE_MOCK_GAUDI}")
    logger.info(f"Gaudi available: {GAUDI_AVAILABLE}")

    load_model()

    yield

    # Cleanup
    logger.info("Shutting down vLLM Gaudi Inference Server")


# FastAPI app
app = FastAPI(
    title="vLLM Gaudi Inference API",
    description="OpenAI-compatible inference API for Intel Gaudi GPUs",
    version="1.0.0-v1",
    lifespan=lifespan
)


@app.get("/health")
async def health():
    """Health check endpoint"""
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    return {
        "status": "healthy",
        "model": model_name,
        "device": str(next(model.parameters()).device),
        "gaudi_available": GAUDI_AVAILABLE,
        "mock_mode": USE_MOCK_GAUDI,
        "version": "1.0.0-v1"
    }


@app.get("/v1/models", response_model=ModelList)
async def list_models():
    """List available models"""
    return ModelList(
        object="list",
        data=[
            ModelInfo(
                id=model_name,
                created=int(datetime.now().timestamp()),
                owned_by="huggingface"
            )
        ]
    )


@app.post("/v1/completions", response_model=CompletionResponse, dependencies=[Depends(verify_api_key)])
async def create_completion(request: CompletionRequest):
    """Generate text completion"""

    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if request.model != model_name:
        raise HTTPException(
            status_code=400,
            detail=f"Model {request.model} not available. Use {model_name}"
        )

    try:
        # Tokenize input
        inputs = tokenizer(
            request.prompt,
            return_tensors="pt",
            padding=True,
            truncation=True
        )

        # Move inputs to same device as model
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        prompt_tokens = inputs['input_ids'].shape[1]

        # Generate
        logger.info(f"Generating completion for prompt: {request.prompt[:50]}...")

        with torch.no_grad():
            outputs = model.generate(
                inputs['input_ids'],
                max_new_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                do_sample=request.temperature > 0,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id
            )

            if str(device) == 'hpu':
                htcore.mark_step()

        # Decode output
        generated_text = tokenizer.decode(
            outputs[0][prompt_tokens:],
            skip_special_tokens=True
        )

        completion_tokens = outputs.shape[1] - prompt_tokens

        logger.info(f"Generated {completion_tokens} tokens")

        # Build response
        return CompletionResponse(
            id=f"cmpl-{uuid.uuid4().hex[:12]}",
            created=int(datetime.now().timestamp()),
            model=model_name,
            choices=[
                CompletionChoice(
                    text=generated_text,
                    index=0,
                    finish_reason="length" if completion_tokens >= request.max_tokens else "stop"
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
        )

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail="Generation failed")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
