"""DigitalOcean PostgreSQL Storage Layer for EloJudge.

Handles persistent storage for:
1. Prioritization runs, rubric receipts, and backlog delivery tiers.
2. User rate limits and quota accounting across restarts.
3. Durable multi-turn rubric and pairwise judgment caches.
"""

from __future__ import annotations

import json
import logging
import ssl
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)

# Global async connection pool
_pool: Optional[asyncpg.Pool] = None


def get_ssl_context() -> ssl.SSLContext:
    """Create SSL context for DigitalOcean managed PostgreSQL connections."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def get_db_pool() -> Optional[asyncpg.Pool]:
    """Retrieve active asyncpg connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    if not settings.database_url:
        logger.info("ℹ️ DATABASE_URL not set — running in in-memory mode.")
        return None

    try:
        # Strip query parameters like sslmode=require for asyncpg connect URL
        dsn = settings.database_url.split("?")[0]
        ssl_ctx = get_ssl_context() if "sslmode" in settings.database_url or "digitalocean" in settings.database_url else None

        _pool = await asyncpg.create_pool(
            dsn,
            ssl=ssl_ctx,
            min_size=1,
            max_size=10,
            command_timeout=15.0,
            max_inactive_connection_lifetime=300.0,
        )
        logger.info(" Connected to DigitalOcean PostgreSQL storage.")
        return _pool
    except Exception as e:
        logger.warning(" Failed to initialize PostgreSQL pool: %s (falling back to in-memory)", e)
        return None


async def init_db() -> None:
    """Create required tables and indexes if they do not exist."""
    pool = await get_db_pool()
    if not pool:
        return

    schema_sql = """
    -- 1. Prioritization Jobs & Backlog Receipts
    CREATE TABLE IF NOT EXISTS ranking_jobs (
        id VARCHAR(64) PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        user_email VARCHAR(255),
        user_ip VARCHAR(64),
        product_context TEXT NOT NULL,
        raw_items_count INT NOT NULL,
        clean_items_count INT NOT NULL,
        ranked_items_count INT NOT NULL,
        summary JSONB NOT NULL,
        rubric JSONB NOT NULL,
        ranked_items JSONB NOT NULL,
        lower_priority_items JSONB NOT NULL DEFAULT '[]'::jsonb,
        matches JSONB NOT NULL DEFAULT '[]'::jsonb,
        cost_estimate NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
        is_byok BOOLEAN NOT NULL DEFAULT FALSE
    );

    CREATE INDEX IF NOT EXISTS idx_ranking_jobs_email ON ranking_jobs (user_email);
    CREATE INDEX IF NOT EXISTS idx_ranking_jobs_created ON ranking_jobs (created_at DESC);

    -- 2. Durable Rubric Cache
    CREATE TABLE IF NOT EXISTS rubric_cache (
        context_hash VARCHAR(32) PRIMARY KEY,
        rubric JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        hit_count INT NOT NULL DEFAULT 0
    );

    -- 3. Durable Pairwise Judgment Cache
    CREATE TABLE IF NOT EXISTS judgment_cache (
        pair_hash VARCHAR(64) PRIMARY KEY,
        winner_text TEXT NOT NULL,
        reason TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.9,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        hit_count INT NOT NULL DEFAULT 0
    );

    -- 4. User Quota & Daily Usage Log
    CREATE TABLE IF NOT EXISTS user_usage_log (
        id BIGSERIAL PRIMARY KEY,
        identifier VARCHAR(255) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_google BOOLEAN NOT NULL DEFAULT FALSE,
        is_byok BOOLEAN NOT NULL DEFAULT FALSE
    );

    CREATE INDEX IF NOT EXISTS idx_user_usage_id_ts ON user_usage_log (identifier, timestamp DESC);
    """

    try:
        async with pool.acquire() as conn:
            await conn.execute(schema_sql)
        logger.info(" PostgreSQL schema initialized successfully.")
    except Exception as e:
        logger.error("❌ Schema initialization error: %s", e)


async def close_db() -> None:
    """Close async connection pool on app shutdown."""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
            logger.info("🛑 PostgreSQL connection pool closed.")
        except Exception as e:
            logger.warning("Error closing PostgreSQL pool: %s", e)
        finally:
            _pool = None


# ── Job Persistence & History ────────────────────────────────────────────────

async def save_ranking_job(
    job_id: str,
    user_email: Optional[str],
    user_ip: str,
    product_context: str,
    raw_items_count: int,
    clean_items_count: int,
    ranked_items_count: int,
    summary_dict: dict[str, Any],
    rubric_dict: dict[str, Any],
    ranked_items_list: list[dict[str, Any]],
    lower_priority_list: list[dict[str, Any]],
    matches_list: list[dict[str, Any]],
    cost_estimate: float,
    is_byok: bool = False,
) -> bool:
    """Persist completed ranking job receipt to PostgreSQL."""
    pool = await get_db_pool()
    if not pool:
        return False

    insert_sql = """
    INSERT INTO ranking_jobs (
        id, user_email, user_ip, product_context, raw_items_count,
        clean_items_count, ranked_items_count, summary, rubric,
        ranked_items, lower_priority_items, matches, cost_estimate, is_byok
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb,
        $10::jsonb, $11::jsonb, $12::jsonb, $13, $14
    )
    ON CONFLICT (id) DO UPDATE SET
        summary = EXCLUDED.summary,
        ranked_items = EXCLUDED.ranked_items,
        matches = EXCLUDED.matches;
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                insert_sql,
                job_id,
                user_email,
                user_ip,
                product_context,
                raw_items_count,
                clean_items_count,
                ranked_items_count,
                json.dumps(summary_dict),
                json.dumps(rubric_dict),
                json.dumps(ranked_items_list),
                json.dumps(lower_priority_list),
                json.dumps(matches_list),
                cost_estimate,
                is_byok,
            )
        logger.info(" Saved ranking job [%s] to DigitalOcean PostgreSQL", job_id)
        return True
    except Exception as e:
        logger.warning("Failed to save ranking job to PostgreSQL: %s", e)
        return False


async def get_recent_jobs(limit: int = 15, user_email: Optional[str] = None) -> list[dict[str, Any]]:
    """Retrieve recent ranking jobs for history display."""
    pool = await get_db_pool()
    if not pool:
        return []

    try:
        async with pool.acquire() as conn:
            if user_email:
                query = """
                SELECT id, created_at, user_email, product_context, raw_items_count,
                       ranked_items_count, cost_estimate, is_byok
                FROM ranking_jobs
                WHERE user_email = $1
                ORDER BY created_at DESC
                LIMIT $2;
                """
                rows = await conn.fetch(query, user_email, limit)
            else:
                query = """
                SELECT id, created_at, user_email, product_context, raw_items_count,
                       ranked_items_count, cost_estimate, is_byok
                FROM ranking_jobs
                ORDER BY created_at DESC
                LIMIT $1;
                """
                rows = await conn.fetch(query, limit)

            return [
                {
                    "id": r["id"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    "user_email": r["user_email"],
                    "product_context": r["product_context"][:120] + "..." if len(r["product_context"]) > 120 else r["product_context"],
                    "raw_items_count": r["raw_items_count"],
                    "ranked_items_count": r["ranked_items_count"],
                    "cost_estimate": float(r["cost_estimate"] or 0.0),
                    "is_byok": bool(r["is_byok"]),
                }
                for r in rows
            ]
    except Exception as e:
        logger.warning("Failed to fetch recent jobs: %s", e)
        return []


async def get_job_by_id(job_id: str) -> Optional[dict[str, Any]]:
    """Fetch complete ranking job payload by ID."""
    pool = await get_db_pool()
    if not pool:
        return None

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM ranking_jobs WHERE id = $1;",
                job_id,
            )
            if not row:
                return None

            return {
                "id": row["id"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                "user_email": row["user_email"],
                "product_context": row["product_context"],
                "raw_items_count": row["raw_items_count"],
                "clean_items_count": row["clean_items_count"],
                "ranked_items_count": row["ranked_items_count"],
                "summary": json.loads(row["summary"]) if isinstance(row["summary"], str) else row["summary"],
                "rubric": json.loads(row["rubric"]) if isinstance(row["rubric"], str) else row["rubric"],
                "ranked_items": json.loads(row["ranked_items"]) if isinstance(row["ranked_items"], str) else row["ranked_items"],
                "lower_priority_candidates": json.loads(row["lower_priority_items"]) if isinstance(row["lower_priority_items"], str) else row["lower_priority_items"],
                "matches": json.loads(row["matches"]) if isinstance(row["matches"], str) else row["matches"],
                "cost_estimate": float(row["cost_estimate"] or 0.0),
                "is_byok": bool(row["is_byok"]),
            }
    except Exception as e:
        logger.warning("Failed to fetch job by ID [%s]: %s", job_id, e)
        return None


# ── Durable User Usage & Quota ───────────────────────────────────────────────

async def record_user_usage_in_db(identifier: str, is_google: bool, is_byok: bool) -> None:
    """Record an execution in persistent PostgreSQL usage log."""
    pool = await get_db_pool()
    if not pool:
        return

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_usage_log (identifier, is_google, is_byok) VALUES ($1, $2, $3);",
                identifier,
                is_google,
                is_byok,
            )
    except Exception as e:
        logger.debug("Failed to record usage in DB: %s", e)


async def get_user_daily_usage_from_db(identifier: str, window_seconds: int = 86400) -> Optional[int]:
    """Get count of runs executed by identifier within rolling window."""
    pool = await get_db_pool()
    if not pool:
        return None

    try:
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM user_usage_log
                WHERE identifier = $1
                  AND is_byok = FALSE
                  AND timestamp > NOW() - make_interval(secs => $2::double precision);
                """,
                identifier,
                float(window_seconds),
            )
            return int(count) if count is not None else 0
    except Exception as e:
        logger.debug("Failed to query usage from DB: %s", e)
        return None
