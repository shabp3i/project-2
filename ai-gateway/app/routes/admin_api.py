"""
Admin REST API routes for user management, token top-ups, upstream config, and logs.
"""

import time
import secrets
import httpx
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from ..config import settings
from ..auth import (
    require_admin,
    create_admin_token,
    generate_user_api_key,
)
from ..database import (
    list_users,
    get_user_by_id,
    create_user,
    topup_user_tokens,
    update_user_status,
    get_recent_logs,
    get_system_stats,
    get_upstream_config,
    set_dynamic_setting,
)
from ..models import (
    AdminLogin,
    AdminLoginResponse,
    UserCreate,
    UserResponse,
    UserTopup,
    UserStatusUpdate,
    UpstreamConfig,
    UpstreamConfigUpdate,
    UpstreamTestResponse,
    RequestLogResponse,
    SystemStatsResponse,
)

router = APIRouter(prefix="/api/admin", tags=["Admin API"])


# --- Admin Authentication ---

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(body: AdminLogin, response: Response):
    """Admin login using password from .env."""
    if not secrets.compare_digest(body.password, settings.ADMIN_PASSWORD):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mật khẩu Admin không chính xác.",
        )

    token = create_admin_token()
    # Set cookie for web browser session
    response.set_cookie(
        key="admin-token",
        value=token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return AdminLoginResponse(token=token, message="Đăng nhập thành công!")


@router.get("/me")
async def admin_check_me(_: bool = Depends(require_admin)):
    """Check if current admin session is valid."""
    return {"authenticated": True, "message": "Phiên đăng nhập hợp lệ."}


@router.post("/logout")
async def admin_logout(response: Response):
    """Clear admin session cookie."""
    response.delete_cookie("admin-token")
    return {"message": "Đã đăng xuất thành công."}


# --- System Statistics ---

@router.get("/stats", response_model=SystemStatsResponse)
async def admin_get_stats(_: bool = Depends(require_admin)):
    """Get high-level system usage and user statistics."""
    stats = await get_system_stats()
    return SystemStatsResponse(
        total_users=stats.get("total_users", 0),
        active_users=stats.get("active_users", 0),
        circulating_tokens=stats.get("circulating_tokens", 0),
        total_tokens_used=stats.get("total_tokens_used", 0),
        total_requests=stats.get("total_requests", 0),
    )


# --- User Management ---

@router.get("/users", response_model=List[UserResponse])
async def admin_list_users(_: bool = Depends(require_admin)):
    """List all users with their balances and lifetime token usage."""
    users = await list_users()
    return users


@router.post("/users", response_model=UserResponse)
async def admin_create_user(body: UserCreate, _: bool = Depends(require_admin)):
    """
    Create a new user.
    Generates a unique API key (sk-user-...) and initializes balance to 0.
    """
    api_key = generate_user_api_key()
    try:
        user = await create_user(username=body.username.strip(), api_key=api_key)
        return user
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tên người dùng '{body.username}' đã tồn tại.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi tạo user: {str(e)}",
        )


@router.post("/users/{user_id}/topup", response_model=UserResponse)
async def admin_topup_user(
    user_id: int, body: UserTopup, _: bool = Depends(require_admin)
):
    """
    Top up tokens for a user after receiving payment in real life.
    Adds body.amount to token_balance.
    """
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng.",
        )

    updated_user = await topup_user_tokens(user_id, body.amount)
    return updated_user


@router.post("/users/{user_id}/status", response_model=UserResponse)
async def admin_update_user_status(
    user_id: int, body: UserStatusUpdate, _: bool = Depends(require_admin)
):
    """Suspend or reactivate a user account."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng.",
        )

    updated_user = await update_user_status(user_id, body.status)
    return updated_user


# --- Upstream Dynamic Configuration ---

@router.get("/settings", response_model=UpstreamConfig)
async def admin_get_settings(_: bool = Depends(require_admin)):
    """Get current upstream configuration."""
    cfg = await get_upstream_config()
    return UpstreamConfig(
        upstream_base_url=cfg["upstream_base_url"],
        upstream_api_key=cfg["upstream_api_key"],
    )


@router.post("/settings", response_model=UpstreamConfig)
async def admin_update_settings(
    body: UpstreamConfigUpdate, _: bool = Depends(require_admin)
):
    """
    Update upstream base URL and API key dynamically without restarting the server.
    """
    url = body.upstream_base_url.strip().rstrip("/")
    api_key = (body.upstream_api_key or "").strip()

    await set_dynamic_setting("upstream_base_url", url)
    await set_dynamic_setting("upstream_api_key", api_key)

    return UpstreamConfig(upstream_base_url=url, upstream_api_key=api_key)


@router.post("/settings/test-upstream", response_model=UpstreamTestResponse)
async def admin_test_upstream(_: bool = Depends(require_admin)):
    """
    Test connectivity to the current upstream backend (Colab ngrok domain).
    Pings GET {upstream_base_url}/models and returns latency and available models.
    """
    cfg = await get_upstream_config()
    target_url = f"{cfg['upstream_base_url']}/models"
    headers = {}
    if cfg["upstream_api_key"]:
        headers["Authorization"] = f"Bearer {cfg['upstream_api_key']}"

    start_t = time.time()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=8.0, connect=5.0)
        ) as client:
            resp = await client.get(target_url, headers=headers)
            latency_ms = round((time.time() - start_t) * 1000, 1)

            if resp.status_code == 200:
                data = resp.json()
                model_names = [m.get("id") for m in data.get("data", []) if "id" in m]
                return UpstreamTestResponse(
                    status="ok",
                    message=f"Kết nối thành công tới Colab! Độ trễ: {latency_ms}ms.",
                    latency_ms=latency_ms,
                    models=model_names,
                )
            else:
                return UpstreamTestResponse(
                    status="warning",
                    message=f"Upstream phản hồi với mã lỗi HTTP {resp.status_code}: {resp.text[:200]}",
                    latency_ms=latency_ms,
                )
    except httpx.ConnectError:
        return UpstreamTestResponse(
            status="error",
            message="Không thể kết nối! Domain ngrok có thể chưa bật hoặc Colab đang tắt.",
        )
    except httpx.TimeoutException:
        return UpstreamTestResponse(
            status="error",
            message="Quá thời gian kết nối (Timeout)! Kiểm tra lại domain ngrok.",
        )
    except Exception as e:
        return UpstreamTestResponse(
            status="error",
            message=f"Lỗi kiểm tra kết nối: {str(e)}",
        )


# --- Request Logs ---

@router.get("/logs", response_model=List[RequestLogResponse])
async def admin_get_logs(limit: int = 100, _: bool = Depends(require_admin)):
    """Fetch recent request logs (timestamp, user, model, token count, duration)."""
    return await get_recent_logs(limit=min(limit, 200))
