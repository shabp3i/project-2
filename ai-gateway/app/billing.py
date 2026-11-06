"""
Billing and token deduction module.
Enforces balance check (HTTP 402) and deducts actual usage from upstream.
"""

from typing import Dict, Any
from fastapi import HTTPException, status
from .database import deduct_user_tokens, log_request


def check_token_balance(user: Dict[str, Any]) -> None:
    """
    Check if user has remaining tokens before forwarding request.
    If token_balance <= 0, reject immediately with HTTP 402.
    If token_balance > 0, allow request to proceed.
    """
    balance = user.get("token_balance", 0)
    if balance <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": {
                    "message": f"Tài khoản của bạn đã hết token (Số dư: {balance:,} token). Vui lòng liên hệ Admin để nạp thêm.",
                    "type": "insufficient_quota",
                    "code": "insufficient_token_balance",
                }
            },
        )


async def record_usage_and_deduct(
    user_id: int,
    username: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    status_code: int,
    duration_ms: int,
) -> Dict[str, Any]:
    """
    Deduct tokens from user's balance and record metadata log.
    Allows balance to go slightly negative if generation exceeds remaining balance,
    which will block subsequent requests.
    """
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens

    updated_user = None
    if total_tokens > 0:
        updated_user = await deduct_user_tokens(user_id, total_tokens)

    # Save audit log (metadata only, no message content)
    await log_request(
        user_id=user_id,
        username=username,
        model=model or "unknown",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        status_code=status_code,
        duration_ms=duration_ms,
    )

    return updated_user or {}


def estimate_tokens_from_text(text: str) -> int:
    """
    Fallback rough token estimation (~4 chars per token for English / ~2-3 chars for code/Vietnamese).
    Only used if upstream backend fails to emit usage statistics.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)
