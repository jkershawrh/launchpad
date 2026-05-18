#!/usr/bin/env python3
"""
Simple inference server using transformers
Compatible with vLLM OpenAI API format for easy migration
"""

import os
import time
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
import uvicorn
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global model and tokenizer
model = None
tokenizer = None
model_name = None
dtype = torch.float32

# API key authentication
API_KEY = os.getenv("API_KEY", "")


async def verify_api_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class CompletionRequest(BaseModel):
    model: str
    prompt: str
    max_tokens: int = Field(default=100, ge=1, le=4096)
    temperature: float = 0.7
    top_p: float = 1.0


class CompletionChoice(BaseModel):
    text: str
    index: int
    finish_reason: str


class CompletionResponse(BaseModel):
    id: str
    object: str = "text_completion"
    created: int
    model: str
    choices: List[CompletionChoice]


@asynccontextmanager
async def lifespan(app):
    """Load model on startup, cleanup on shutdown"""
    global model, tokenizer, model_name, dtype

    # Get model name from environment or use default
    model_name = os.getenv("MODEL_NAME", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
    use_bf16 = os.getenv("USE_BF16", "true").lower() == "true"
    dtype = torch.bfloat16 if use_bf16 else torch.float32

    logger.info(f"Loading model: {model_name}")
    logger.info(f"Device: CPU | dtype: {dtype}")

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=dtype,
            device_map="cpu",
            low_cpu_mem_usage=True
        )
        logger.info(f"Model loaded successfully (BF16: {use_bf16})")
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        raise

    yield

    # Cleanup
    logger.info("Shutting down inference server")


app = FastAPI(title="CPU Inference Server", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint"""
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "status": "healthy",
        "model": model_name,
        "dtype": str(next(model.parameters()).dtype),
        "accelerator": "xeon6",
    }


@app.get("/v1/models")
async def list_models():
    """List available models"""
    return {
        "object": "list",
        "data": [
            {
                "id": model_name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local"
            }
        ]
    }


@app.post("/v1/completions", dependencies=[Depends(verify_api_key)])
async def create_completion(request: CompletionRequest) -> CompletionResponse:
    """Generate text completion"""
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        # Tokenize input
        inputs = tokenizer(request.prompt, return_tensors="pt")

        # Generate with BF16 autocast for AMX acceleration
        with torch.no_grad(), torch.cpu.amp.autocast(dtype=dtype):
            outputs = model.generate(
                inputs.input_ids,
                max_new_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                do_sample=True if request.temperature > 0 else False,
                pad_token_id=tokenizer.eos_token_id
            )

        # Extract completion using token offsets (not character slicing)
        prompt_tokens = inputs.input_ids.shape[1]
        completion_tokens = outputs[0][prompt_tokens:]
        completion_text = tokenizer.decode(completion_tokens, skip_special_tokens=True)

        return CompletionResponse(
            id=f"cmpl-{uuid.uuid4().hex[:12]}",
            created=int(time.time()),
            model=model_name,
            choices=[
                CompletionChoice(
                    text=completion_text,
                    index=0,
                    finish_reason="stop"
                )
            ]
        )

    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail="Inference error")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "CPU Inference Server",
        "model": model_name,
        "endpoints": ["/health", "/v1/models", "/v1/completions"]
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
