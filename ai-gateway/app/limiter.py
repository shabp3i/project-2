"""
In-memory sliding window rate limiter per user API key.
"""

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, status
from .config import settings

# Stores timestamps of requests for each user ID
_request_windows: Dict[int, List[float]] = defaultdict(list)


def check_rate_limit(user_id: int) -> None:
    """
    Check if the user has exceeded the rate limit.
    Raises HTTP 429 if limit is exceeded.
    """
    now = time.time()
    window_start = now - 60.0  # 1 minute window

    timestamps = _request_windows[user_id]
    # Filter out timestamps older than 60 seconds
    _request_windows[user_id] = [t for t in timestamps if t > window_start]

    if len(_request_windows[user_id]) >= settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "message": f"Bạn đang gửi request quá nhanh. Giới hạn: {settings.RATE_LIMIT_PER_MINUTE} request/phút. Vui lòng chậm lại.",
                    "type": "rate_limit_exceeded",
                    "code": "rate_limit",
                }
            },
        )

    _request_windows[user_id].append(now)


def clear_expired_rate_limits() -> None:
    """Prune stale users from memory."""
    now = time.time()
    cutoff = now - 120.0
    for uid in list(_request_windows.keys()):
        _request_windows[uid] = [t for t in _request_windows[uid] if t > cutoff]
        if not _request_windows[uid]:
            del _request_windows[uid]
