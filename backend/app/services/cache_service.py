"""
services/cache_service.py
─────────────────────────
Redis cache layer.
Provides typed get/set/delete with automatic JSON serialisation,
TTL management, and pattern-based invalidation.

Used for:
  - Rate limiting (sliding window counter)
  - Session data caching
  - Hot-path query result caching (note lists, tag lists)
  - Idempotency keys
"""

from __future__ import annotations
import json
import logging
from typing import Any, Optional
from datetime import timedelta

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Key prefixes — keep all keys namespaced to avoid collisions
PREFIX_RATE_LIMIT   = "rl:"
PREFIX_NOTE_LIST    = "notes:list:"
PREFIX_TAG_LIST     = "tags:"
PREFIX_USER_STATS   = "stats:"
PREFIX_IDEMPOTENCY  = "idem:"
PREFIX_SESSION      = "sess:"


class CacheService:
    """
    Async Redis cache service.
    Connects lazily on first use. Gracefully degrades on Redis errors
    (returns None / False) so the API keeps working without cache.
    """

    def __init__(self):
        self._client: Optional[Redis] = None

    async def _get_client(self) -> Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True,
                max_connections=20,
            )
        return self._client

    # ── Core get / set / delete ───────────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        """Return deserialised value or None on miss/error."""
        try:
            client = await self._get_client()
            raw = await client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except RedisError as e:
            logger.warning(f"Cache GET error [{key}]: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300,
    ) -> bool:
        """Serialise and store value with TTL in seconds. Returns success."""
        try:
            client = await self._get_client()
            await client.set(key, json.dumps(value, default=str), ex=ttl)
            return True
        except RedisError as e:
            logger.warning(f"Cache SET error [{key}]: {e}")
            return False

    async def delete(self, key: str) -> bool:
        try:
            client = await self._get_client()
            await client.delete(key)
            return True
        except RedisError as e:
            logger.warning(f"Cache DELETE error [{key}]: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern (use sparingly — SCAN based)."""
        try:
            client = await self._get_client()
            count = 0
            async for key in client.scan_iter(match=pattern, count=100):
                await client.delete(key)
                count += 1
            return count
        except RedisError as e:
            logger.warning(f"Cache DELETE PATTERN error [{pattern}]: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        try:
            client = await self._get_client()
            return bool(await client.exists(key))
        except RedisError:
            return False

    # ── Rate limiting (sliding window) ────────────────────────────

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int = 120,
        window_seconds: int = 60,
    ) -> tuple[bool, int]:
        """
        Sliding window rate limiter.
        Returns (allowed: bool, remaining: int).
        Falls back to (True, limit) if Redis is unavailable.
        """
        key = f"{PREFIX_RATE_LIMIT}{identifier}"
        try:
            client = await self._get_client()
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            results = await pipe.execute()
            count = results[0]
            remaining = max(0, limit - count)
            return count <= limit, remaining
        except RedisError as e:
            logger.warning(f"Rate limit check failed: {e}")
            return True, limit   # fail open

    # ── Typed cache helpers ───────────────────────────────────────

    async def get_note_list(self, user_id: str, cache_key: str) -> Optional[list]:
        return await self.get(f"{PREFIX_NOTE_LIST}{user_id}:{cache_key}")

    async def set_note_list(
        self, user_id: str, cache_key: str, data: list, ttl: int = 60
    ):
        await self.set(f"{PREFIX_NOTE_LIST}{user_id}:{cache_key}", data, ttl=ttl)

    async def invalidate_note_list(self, user_id: str):
        """Call after any note create/update/delete."""
        await self.delete_pattern(f"{PREFIX_NOTE_LIST}{user_id}:*")

    async def get_tags(self, user_id: str) -> Optional[list]:
        return await self.get(f"{PREFIX_TAG_LIST}{user_id}")

    async def set_tags(self, user_id: str, data: list, ttl: int = 300):
        await self.set(f"{PREFIX_TAG_LIST}{user_id}", data, ttl=ttl)

    async def invalidate_tags(self, user_id: str):
        await self.delete(f"{PREFIX_TAG_LIST}{user_id}")

    async def get_user_stats(self, user_id: str) -> Optional[dict]:
        return await self.get(f"{PREFIX_USER_STATS}{user_id}")

    async def set_user_stats(self, user_id: str, data: dict, ttl: int = 120):
        await self.set(f"{PREFIX_USER_STATS}{user_id}", data, ttl=ttl)

    async def invalidate_user_stats(self, user_id: str):
        await self.delete(f"{PREFIX_USER_STATS}{user_id}")

    # ── Idempotency keys ──────────────────────────────────────────

    async def set_idempotency(self, key: str, response: Any, ttl: int = 86400):
        await self.set(f"{PREFIX_IDEMPOTENCY}{key}", response, ttl=ttl)

    async def get_idempotency(self, key: str) -> Optional[Any]:
        return await self.get(f"{PREFIX_IDEMPOTENCY}{key}")

    # ── Health check ──────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            client = await self._get_client()
            return await client.ping()
        except RedisError:
            return False

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


cache_service = CacheService()
