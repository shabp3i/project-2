"""
Pydantic schemas and models for AI Gateway.
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field


# --- Admin & User Management Schemas ---

class AdminLogin(BaseModel):
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    message: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)


class UserResponse(BaseModel):
    id: int
    username: str
    api_key: str
    token_balance: int
    lifetime_tokens_used: int
    status: str
    created_at: str
    last_active_at: Optional[str] = None


class UserTopup(BaseModel):
    amount: int = Field(..., gt=0, description="Số lượng token muốn cộng vào tài khoản")


class UserStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|suspended)$")


class UpstreamConfig(BaseModel):
    upstream_base_url: str
    upstream_api_key: str = ""


class UpstreamConfigUpdate(BaseModel):
    upstream_base_url: str = Field(..., min_length=5)
    upstream_api_key: Optional[str] = ""


class UpstreamTestResponse(BaseModel):
    status: str
    message: str
    latency_ms: Optional[float] = None
    models: Optional[List[str]] = None


class RequestLogResponse(BaseModel):
    id: int
    user_id: int
    username: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    status_code: int
    duration_ms: int
    created_at: str


class SystemStatsResponse(BaseModel):
    total_users: int
    active_users: int
    circulating_tokens: int
    total_tokens_used: int
    total_requests: int


# --- OpenAI Error Schema ---

class OpenAIErrorDetail(BaseModel):
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None


class OpenAIErrorResponse(BaseModel):
    error: OpenAIErrorDetail
