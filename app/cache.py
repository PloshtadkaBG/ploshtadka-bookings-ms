import json
from uuid import UUID

from loguru import logger
from redis.asyncio import Redis

from app.settings import REDIS_URL

_redis: Redis | None = None
SLOTS_TTL = 60  # 1 minute


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _slots_key(venue_id: UUID) -> str:
    return f"slots:{venue_id}"


async def get_slots_cache(venue_id: UUID) -> list | None:
    try:
        data = await get_redis().get(_slots_key(venue_id))
        return json.loads(data) if data else None
    except Exception:
        logger.warning("Redis get failed — skipping slots cache", exc_info=True)
        return None


async def set_slots_cache(venue_id: UUID, slots: list) -> None:
    try:
        await get_redis().setex(_slots_key(venue_id), SLOTS_TTL, json.dumps(slots))
    except Exception:
        logger.warning("Redis set failed — skipping slots cache", exc_info=True)


async def invalidate_slots_cache(venue_id: UUID) -> None:
    try:
        await get_redis().delete(_slots_key(venue_id))
    except Exception:
        logger.warning("Redis invalidate failed for slots cache", exc_info=True)
