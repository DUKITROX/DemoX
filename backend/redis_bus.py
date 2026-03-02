import json
import redis.asyncio as redis
from backend.config import REDIS_URL

_redis = None


async def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def publish_research(room_id: str, data: dict):
    """Publish research results for a room."""
    r = await get_redis()
    await r.set(f"research:{room_id}", json.dumps(data))
    await r.publish(f"research_updates:{room_id}", json.dumps(data))


async def get_research(room_id: str) -> dict | None:
    """Get current research data for a room."""
    r = await get_redis()
    raw = await r.get(f"research:{room_id}")
    if raw:
        return json.loads(raw)
    return None


async def publish_agent_request(room_id: str, request: dict):
    """Presenter agent requests deeper research on a topic."""
    r = await get_redis()
    await r.publish(f"agent_requests:{room_id}", json.dumps(request))


async def publish_agent_action(room_id: str, action: dict):
    """Broadcast agent action (for frontend status display)."""
    r = await get_redis()
    await r.publish(f"agent_actions:{room_id}", json.dumps(action))


async def set_room_metadata(room_id: str, data: dict):
    """Store room metadata (URL, status, etc.)."""
    r = await get_redis()
    await r.set(f"room:{room_id}", json.dumps(data), ex=3600)  # 1h TTL


async def get_room_metadata(room_id: str) -> dict | None:
    r = await get_redis()
    raw = await r.get(f"room:{room_id}")
    if raw:
        return json.loads(raw)
    return None


async def cleanup_room(room_id: str):
    """Remove all Redis keys for a room."""
    r = await get_redis()
    await r.delete(
        f"research:{room_id}",
        f"room:{room_id}",
    )
