"""
Configuration module for AI Gateway.
Reads settings from environment variables or .env file.
"""

import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Upstream backend (Colab / llama.cpp via ngrok)
    UPSTREAM_BASE_URL: str = "https://your-ngrok-domain.ngrok-free.app/v1"
    UPSTREAM_API_KEY: str = ""

    # Admin Panel Authentication
    ADMIN_PASSWORD: str = "admin123456"
    SECRET_KEY: str = secrets.token_hex(32)

    # SQLite Database File Path
    DB_PATH: str = "data/gateway.db"

    # Rate Limiting (requests per minute per API key)
    RATE_LIMIT_PER_MINUTE: int = 60

    # HTTP timeouts (seconds)
    CONNECT_TIMEOUT: float = 10.0
    READ_TIMEOUT: float = 300.0

    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure data directory exists
db_dir = Path(settings.DB_PATH).parent
db_dir.mkdir(parents=True, exist_ok=True)
