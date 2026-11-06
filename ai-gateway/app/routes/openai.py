"""
OpenAI-compatible endpoints (/v1/chat/completions, /v1/models).
Receives calls from OpenCode client and proxies them upstream.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..auth import get_current_user
from ..billing import check_token_balance
from ..limiter import check_rate_limit
from ..database import get_upstream_config
from ..proxy import (
    forward_models_request,
    handle_non_streaming_chat,
    handle_streaming_chat,
)

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])


@router.get("/models")
async def list_models(request: Request):
    """
    List available models.
    Proxies to upstream backend or returns fallback list if upstream is asleep.
    """
    return await forward_models_request()


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    """Get single model metadata."""
    return {
        "id": model_id,
        "object": "model",
        "created": 1700000000,
        "owned_by": "colab-llama-cpp",
    }


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    OpenAI-compatible chat completion endpoint.
    1. Authenticates user API key.
    2. Enforces rate limits.
    3. Checks token balance (> 0 required).
    4. Forwards to upstream llama.cpp server on Colab.
    5. Deducts actual tokens used (prompt + completion) from user balance.
    """
    # 1. Rate limit check
    check_rate_limit(user["id"])

    # 2. Token balance check (> 0 required to start request)
    check_token_balance(user)

    # 3. Parse request payload
    payload = await request.json()
    is_stream = bool(payload.get("stream", False))

    # 4. Fetch dynamic upstream settings
    upstream = await get_upstream_config()
    upstream_base_url = upstream["upstream_base_url"]
    upstream_api_key = upstream["upstream_api_key"]

    # 5. Route to streaming or non-streaming handler
    if is_stream:
        return await handle_streaming_chat(
            payload=payload,
            user=user,
            upstream_base_url=upstream_base_url,
            upstream_api_key=upstream_api_key,
        )
    else:
        return await handle_non_streaming_chat(
            payload=payload,
            user=user,
            upstream_base_url=upstream_base_url,
            upstream_api_key=upstream_api_key,
        )
