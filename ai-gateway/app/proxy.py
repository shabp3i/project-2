"""
Proxy module for forwarding OpenAI-compatible requests to the upstream backend (llama.cpp server).
Handles both streaming (SSE) and non-streaming modes, extracts real token usage,
and handles connection errors gracefully (503 Service Unavailable).
"""

import time
import json
import logging
from typing import Dict, Any, AsyncGenerator, Tuple, Optional
import httpx
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse

from .config import settings
from .database import get_upstream_config
from .billing import record_usage_and_deduct, estimate_tokens_from_text

logger = logging.getLogger("gateway.proxy")


def build_upstream_headers(upstream_api_key: str) -> Dict[str, str]:
    """Build headers for forwarding to upstream backend."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if upstream_api_key:
        headers["Authorization"] = f"Bearer {upstream_api_key}"
    return headers


async def forward_models_request() -> JSONResponse:
    """
    Forward GET /v1/models to upstream backend.
    If upstream is offline, return a fallback model list so client can start without crashing.
    """
    upstream = await get_upstream_config()
    upstream_url = f"{upstream['upstream_base_url']}/models"
    headers = build_upstream_headers(upstream['upstream_api_key'])

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=10.0, connect=5.0)
        ) as client:
            resp = await client.get(upstream_url, headers=headers)
            if resp.status_code == 200:
                return JSONResponse(content=resp.json(), status_code=200)
            logger.warning(f"Upstream models returned status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Could not reach upstream /models ({e}), serving fallback models list")

    # Fallback model list if upstream is sleeping or starting up
    fallback_data = {
        "object": "list",
        "data": [
            {
                "id": "default",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "colab-llama-cpp",
                "permission": [],
                "root": "default",
                "parent": None,
            },
            {
                "id": "llama-3-8b-instruct",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "colab-llama-cpp",
                "permission": [],
                "root": "llama-3-8b-instruct",
                "parent": None,
            },
            {
                "id": "qwen-2.5-coder",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "colab-llama-cpp",
                "permission": [],
                "root": "qwen-2.5-coder",
                "parent": None,
            },
        ],
    }
    return JSONResponse(content=fallback_data, status_code=200)


async def handle_non_streaming_chat(
    payload: Dict[str, Any],
    user: Dict[str, Any],
    upstream_base_url: str,
    upstream_api_key: str,
) -> JSONResponse:
    """Handle standard non-streaming chat completion."""
    start_time = time.time()
    url = f"{upstream_base_url}/chat/completions"
    headers = build_upstream_headers(upstream_api_key)
    model_name = payload.get("model", "default")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=settings.READ_TIMEOUT, connect=settings.CONNECT_TIMEOUT)
        ) as client:
            response = await client.post(url, json=payload, headers=headers)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        logger.error(f"Failed to connect to upstream {url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "message": "Không thể kết nối tới máy chủ AI (Google Colab / llama.cpp). Server có thể đang tắt hoặc ngrok tunnel chưa hoạt động.",
                    "type": "upstream_unavailable",
                    "code": "upstream_offline",
                }
            },
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error": {
                    "message": "Máy chủ AI phản hồi quá lâu (Timeout). Vui lòng thử lại.",
                    "type": "gateway_timeout",
                    "code": "read_timeout",
                }
            },
        )
    except Exception as e:
        logger.error(f"Error communicating with upstream: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "message": f"Lỗi cổng kết nối upstream: {str(e)}",
                    "type": "bad_gateway",
                    "code": "upstream_error",
                }
            },
        )

    duration_ms = int((time.time() - start_time) * 1000)

    if response.status_code != 200:
        # Pass through upstream error
        try:
            err_data = response.json()
        except Exception:
            err_data = {"error": {"message": response.text}}
        return JSONResponse(content=err_data, status_code=response.status_code)

    data = response.json()
    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

    # Fallback token estimate if upstream didn't send usage
    if total_tokens <= 0:
        choices = data.get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        completion_tokens = estimate_tokens_from_text(content)
        prompt_tokens = estimate_tokens_from_text(str(payload.get("messages", "")))
        total_tokens = prompt_tokens + completion_tokens

    # Deduct tokens from user's balance
    await record_usage_and_deduct(
        user_id=user["id"],
        username=user["username"],
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    return JSONResponse(content=data, status_code=200)


async def handle_streaming_chat(
    payload: Dict[str, Any],
    user: Dict[str, Any],
    upstream_base_url: str,
    upstream_api_key: str,
) -> StreamingResponse:
    """
    Handle streaming chat completions (SSE).
    Injects stream_options.include_usage = True so upstream emits usage.
    Yields chunks to client immediately while parsing usage on the fly.
    Deducts balance in a guaranteed finally block.
    """
    start_time = time.time()
    url = f"{upstream_base_url}/chat/completions"
    headers = build_upstream_headers(upstream_api_key)
    model_name = payload.get("model", "default")

    # Request usage in streaming chunks from OpenAI / llama.cpp
    if "stream_options" not in payload:
        payload["stream_options"] = {"include_usage": True}
    elif isinstance(payload["stream_options"], dict):
        payload["stream_options"]["include_usage"] = True

    # Pre-test connection before returning streaming response so we catch connection errors as clean 503
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout=settings.READ_TIMEOUT, connect=settings.CONNECT_TIMEOUT)
    )

    try:
        req = client.build_request("POST", url, json=payload, headers=headers)
        upstream_resp = await client.send(req, stream=True)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        await client.aclose()
        logger.error(f"Stream connect error to upstream {url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "message": "Không thể kết nối tới máy chủ AI (Google Colab / llama.cpp). Server có thể đang tắt hoặc ngrok tunnel chưa hoạt động.",
                    "type": "upstream_unavailable",
                    "code": "upstream_offline",
                }
            },
        )
    except Exception as e:
        await client.aclose()
        logger.error(f"Stream build error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "message": f"Lỗi khởi tạo luồng upstream: {str(e)}",
                    "type": "bad_gateway",
                    "code": "upstream_error",
                }
            },
        )

    if upstream_resp.status_code != 200:
        err_body = await upstream_resp.aread()
        await upstream_resp.aclose()
        await client.aclose()
        try:
            err_json = json.loads(err_body.decode("utf-8"))
        except Exception:
            err_json = {"error": {"message": err_body.decode("utf-8", errors="ignore")}}
        return JSONResponse(content=err_json, status_code=upstream_resp.status_code)

    async def event_generator() -> AsyncGenerator[bytes, None]:
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        collected_text = []
        status_code = 200
        buffer = ""

        try:
            async for chunk in upstream_resp.aiter_bytes():
                yield chunk

                # Buffer and parse SSE lines to extract usage
                buffer += chunk.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        continue

                    try:
                        chunk_obj = json.loads(data_str)
                        # 1. Standard OpenAI / llama.cpp usage object in stream
                        if "usage" in chunk_obj and chunk_obj["usage"]:
                            u = chunk_obj["usage"]
                            p = u.get("prompt_tokens", 0)
                            c = u.get("completion_tokens", 0)
                            t = u.get("total_tokens", p + c)
                            if t > 0:
                                prompt_tokens = p
                                completion_tokens = c
                                total_tokens = t
                        # 2. llama.cpp server timings object
                        elif "timings" in chunk_obj and chunk_obj["timings"]:
                            tm = chunk_obj["timings"]
                            prompt_tokens = tm.get("prompt_n", prompt_tokens)
                            completion_tokens = tm.get("predicted_n", completion_tokens)
                            total_tokens = prompt_tokens + completion_tokens

                        # Collect chunk text for fallback token estimation if usage missing
                        choices = chunk_obj.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content_piece = delta.get("content", "")
                            if content_piece:
                                collected_text.append(content_piece)
                    except Exception:
                        pass
        except Exception as ex:
            logger.error(f"Error while streaming response: {ex}")
            status_code = 500
        finally:
            # Always close upstream connections
            try:
                await upstream_resp.aclose()
                await client.aclose()
            except Exception:
                pass

            duration_ms = int((time.time() - start_time) * 1000)

            # Fallback token estimation if upstream didn't send usage chunk
            if total_tokens <= 0:
                completion_tokens = estimate_tokens_from_text("".join(collected_text))
                prompt_tokens = estimate_tokens_from_text(str(payload.get("messages", "")))
                total_tokens = prompt_tokens + completion_tokens

            # Deduct tokens from user's balance and save request log
            try:
                await record_usage_and_deduct(
                    user_id=user["id"],
                    username=user["username"],
                    model=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
            except Exception as e:
                logger.error(f"Failed to record token usage in stream finally: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
