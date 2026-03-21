"""Event storage and retrieval for instructor browsing events from the Chrome extension."""

import json
import logging
import time

import redis.asyncio as aioredis
from backend.config import REDIS_URL

logger = logging.getLogger(__name__)

# Redis key patterns:
#   instructor_events:{room_id}      — sorted set of events (score = timestamp)
#   instructor_events_stream:{room_id} — pub/sub channel for real-time event streaming


async def store_events(room_id: str, events: list[dict]) -> int:
    """Store a batch of events in Redis sorted set + publish to stream.

    Returns the number of events stored.
    """
    if not events:
        return 0

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        pipe = r.pipeline()
        for event in events:
            ts = event.get("timestamp", time.time())
            pipe.zadd(
                f"instructor_events:{room_id}",
                {json.dumps(event): ts},
            )
            # Publish each event for real-time listeners (agent)
            pipe.publish(
                f"instructor_events_stream:{room_id}",
                json.dumps(event),
            )
        await pipe.execute()

        # Set TTL on the sorted set (1 hour)
        await r.expire(f"instructor_events:{room_id}", 3600)

        logger.info(f"Stored {len(events)} events for room {room_id}")
        return len(events)
    finally:
        await r.aclose()


async def get_events(room_id: str, since: float = 0, limit: int = 1000) -> list[dict]:
    """Retrieve events from Redis sorted set.

    Args:
        room_id: The room to fetch events for.
        since: Only return events with timestamp > since (0 = all).
        limit: Maximum number of events to return.
    """
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        if since > 0:
            # Get events after timestamp
            raw = await r.zrangebyscore(
                f"instructor_events:{room_id}",
                min=since,
                max="+inf",
                start=0,
                num=limit,
            )
        else:
            # Get all events (up to limit)
            raw = await r.zrange(
                f"instructor_events:{room_id}",
                0, limit - 1,
            )
        return [json.loads(item) for item in raw]
    finally:
        await r.aclose()


async def get_recent_events(room_id: str, seconds: float = 15.0) -> list[dict]:
    """Get events from the last N seconds. Used by save_learning to snapshot recent context."""
    since = time.time() - seconds
    return await get_events(room_id, since=since, limit=200)


async def get_event_count(room_id: str) -> int:
    """Get total event count for a room."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        return await r.zcard(f"instructor_events:{room_id}")
    finally:
        await r.aclose()


async def cleanup_events(room_id: str):
    """Delete all events for a room."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.delete(f"instructor_events:{room_id}")
    finally:
        await r.aclose()
