"""
Database module for AI Gateway using SQLite via aiosqlite.
Manages users, dynamic system settings, and request logs.
"""

import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Dict, Any, List
from .config import settings


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Provide an async database connection with WAL mode enabled."""
    db = await aiosqlite.connect(settings.DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA synchronous = NORMAL;")
        await db.execute("PRAGMA busy_timeout = 5000;")
        yield db
    finally:
        await db.close()


async def init_db() -> None:
    """Initialize database tables and default dynamic settings."""
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                api_key TEXT NOT NULL UNIQUE,
                token_balance INTEGER NOT NULL DEFAULT 0,
                lifetime_tokens_used INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                last_active_at TEXT
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                status_code INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_created_at ON request_logs(created_at DESC);")
        await db.commit()


# --- Database Helper Functions ---

async def get_user_by_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Retrieve user dictionary by API key."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE api_key = ?", (api_key,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve user dictionary by user ID."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def list_users() -> List[Dict[str, Any]]:
    """List all users sorted by ID descending."""
    async with get_db() as db:
        async with db.execute(
            "SELECT id, username, api_key, token_balance, lifetime_tokens_used, status, created_at, last_active_at FROM users ORDER BY id DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def create_user(username: str, api_key: str) -> Dict[str, Any]:
    """Create a new user with 0 initial token balance."""
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO users (username, api_key, token_balance, lifetime_tokens_used, status) VALUES (?, ?, 0, 0, 'active')",
            (username, api_key),
        )
        await db.commit()
        user_id = cursor.lastrowid
        return await get_user_by_id(user_id)


async def topup_user_tokens(user_id: int, amount: int) -> Optional[Dict[str, Any]]:
    """Add tokens directly to user balance."""
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET token_balance = token_balance + ? WHERE id = ?",
            (amount, user_id),
        )
        await db.commit()
        return await get_user_by_id(user_id)


async def update_user_status(user_id: int, status: str) -> Optional[Dict[str, Any]]:
    """Update user status ('active' or 'suspended')."""
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET status = ? WHERE id = ?",
            (status, user_id),
        )
        await db.commit()
        return await get_user_by_id(user_id)


async def deduct_user_tokens(
    user_id: int, tokens_to_deduct: int
) -> Optional[Dict[str, Any]]:
    """
    Atomically deduct token_balance, increment lifetime_tokens_used,
    and update last_active_at.
    """
    async with get_db() as db:
        await db.execute(
            """
            UPDATE users
            SET token_balance = token_balance - ?,
                lifetime_tokens_used = lifetime_tokens_used + ?,
                last_active_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (tokens_to_deduct, tokens_to_deduct, user_id),
        )
        await db.commit()
        return await get_user_by_id(user_id)


async def log_request(
    user_id: int,
    username: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    status_code: int,
    duration_ms: int,
) -> None:
    """Log request metadata without storing prompt/completion content."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO request_logs
            (user_id, username, model, prompt_tokens, completion_tokens, total_tokens, status_code, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                status_code,
                duration_ms,
            ),
        )
        await db.commit()


async def get_recent_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch recent request logs."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM request_logs ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_system_stats() -> Dict[str, Any]:
    """Retrieve overall system statistics."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT
                COUNT(*) as total_users,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_users,
                COALESCE(SUM(token_balance), 0) as circulating_tokens,
                COALESCE(SUM(lifetime_tokens_used), 0) as total_tokens_used
            FROM users
            """
        ) as cursor:
            row = await cursor.fetchone()
            stats = dict(row) if row else {}

        async with db.execute("SELECT COUNT(*) as total_requests FROM request_logs") as cursor:
            req_row = await cursor.fetchone()
            stats["total_requests"] = req_row["total_requests"] if req_row else 0

        return stats


# --- Dynamic Upstream Configuration Helpers ---

async def get_dynamic_setting(key: str, default: str = "") -> str:
    """Retrieve setting from DB or return default."""
    async with get_db() as db:
        async with db.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row["value"]:
                return row["value"]
            return default


async def set_dynamic_setting(key: str, value: str) -> None:
    """Upsert setting in DB."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO system_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value.strip()),
        )
        await db.commit()


async def get_upstream_config() -> Dict[str, str]:
    """
    Get effective upstream base URL and API key.
    Checks DB dynamic settings first, falling back to .env values.
    """
    base_url = await get_dynamic_setting("upstream_base_url", settings.UPSTREAM_BASE_URL)
    api_key = await get_dynamic_setting("upstream_api_key", settings.UPSTREAM_API_KEY)
    # Ensure no trailing slash
    return {
        "upstream_base_url": base_url.rstrip("/"),
        "upstream_api_key": api_key,
    }
