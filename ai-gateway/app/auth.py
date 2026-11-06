"""
Authentication module for AI Gateway.
Handles user API key validation and Admin token generation/verification.
"""

import time
import json
import base64
import hmac
import hashlib
import secrets
from typing import Dict, Any, Optional
from fastapi import HTTPException, Security, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings
from .database import get_user_by_api_key

security_bearer = HTTPBearer(auto_error=False)


# --- User API Key Verification ---

def generate_user_api_key() -> str:
    """Generate a unique API key with prefix sk-user- followed by 32 hex chars."""
    return f"sk-user-{secrets.token_hex(16)}"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> Dict[str, Any]:
    """
    Authenticate user request via API key.
    Checks Authorization: Bearer <key> or x-api-key header.
    """
    api_key: Optional[str] = None

    if credentials and credentials.credentials:
        api_key = credentials.credentials
    elif "x-api-key" in request.headers:
        api_key = request.headers["x-api-key"]

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "Thiếu API key. Vui lòng cung cấp Authorization: Bearer sk-user-...",
                    "type": "invalid_request_error",
                    "code": "missing_api_key",
                }
            },
        )

    user = await get_user_by_api_key(api_key.strip())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "API key không hợp lệ hoặc không tồn tại.",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
        )

    if user["status"] == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "message": "Tài khoản của bạn đang bị tạm khoá. Vui lòng liên hệ Admin.",
                    "type": "account_suspended",
                    "code": "user_suspended",
                }
            },
        )

    return user


# --- Admin Session Token (HMAC-SHA256 based) ---

def create_admin_token() -> str:
    """Create a signed admin session token valid for 7 days."""
    payload = {
        "role": "admin",
        "exp": int(time.time()) + (7 * 24 * 3600),
        "nonce": secrets.token_hex(8),
    }
    raw_payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_payload).decode("utf-8").rstrip("=")
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        b64_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{b64_payload}.{signature}"


def verify_admin_token(token: str) -> bool:
    """Verify admin token integrity and expiration."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False
        b64_payload, signature = parts
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            b64_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not secrets.compare_digest(signature, expected_sig):
            return False

        # Add padding back if necessary
        rem = len(b64_payload) % 4
        padded = b64_payload + ("=" * (4 - rem) if rem else "")
        raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(raw)

        if payload.get("role") != "admin":
            return False
        if payload.get("exp", 0) < time.time():
            return False

        return True
    except Exception:
        return False


async def require_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> bool:
    """FastAPI dependency protecting admin endpoints."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "admin-token" in request.cookies:
        token = request.cookies.get("admin-token")
    elif "x-admin-token" in request.headers:
        token = request.headers.get("x-admin-token")

    if not token or not verify_admin_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu quyền Admin hoặc phiên đăng nhập đã hết hạn.",
        )
    return True
