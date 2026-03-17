"""Data structures and Redis persistence for presenter agent mode state."""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Literal

import redis.asyncio as aioredis


@dataclass
class Learning:
    topic: str
    details: str
    page_url: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class DemoRoadmap:
    steps: list[dict]  # [{step, page, action, target_text, narration, if_not_found}]
    opening_line: str
    closing_line: str


@dataclass
class ModeState:
    mode: Literal["student", "demo_expert"] = "student"
    learnings: list[Learning] = field(default_factory=list)
    roadmap: DemoRoadmap | None = None
    demo_feedback_requested: bool = False

    def upsert_learning(self, topic: str, details: str, page_url: str) -> bool:
        """Insert or update a learning by topic. Returns True if updated, False if inserted."""
        topic_lower = topic.lower()
        for i, l in enumerate(self.learnings):
            if l.topic.lower() == topic_lower:
                self.learnings[i] = Learning(
                    topic=topic, details=details,
                    page_url=page_url, timestamp=time.time(),
                )
                return True
        self.learnings.append(Learning(
            topic=topic, details=details,
            page_url=page_url, timestamp=time.time(),
        ))
        return False

    def remove_learning(self, topic: str) -> int:
        """Remove all learnings matching topic (case-insensitive). Returns count removed."""
        topic_lower = topic.lower()
        before = len(self.learnings)
        self.learnings = [l for l in self.learnings if l.topic.lower() != topic_lower]
        return before - len(self.learnings)


def learnings_to_text(learnings: list[Learning]) -> str:
    """Format learnings as a running notepad for embedding in instructions."""
    if not learnings:
        return "(No notes yet — still learning!)"
    lines = []
    for i, l in enumerate(learnings, 1):
        lines.append(f"{i}. **{l.topic}**: {l.details}")
        if l.page_url:
            lines.append(f"   (Page: {l.page_url})")
    return "\n".join(lines)


def _state_to_dict(state: ModeState) -> dict:
    """Serialize ModeState to a JSON-compatible dict."""
    d = {
        "mode": state.mode,
        "learnings": [asdict(l) for l in state.learnings],
        "demo_feedback_requested": state.demo_feedback_requested,
    }
    if state.roadmap:
        d["roadmap"] = asdict(state.roadmap)
    return d


def _state_from_dict(d: dict) -> ModeState:
    """Deserialize ModeState from a dict."""
    state = ModeState(mode=d.get("mode", "student"))
    state.demo_feedback_requested = d.get("demo_feedback_requested", False)
    for ld in d.get("learnings", []):
        state.learnings.append(Learning(**ld))
    rd = d.get("roadmap")
    if rd:
        state.roadmap = DemoRoadmap(**rd)
    return state


async def save_mode_state_to_redis(state: ModeState, room_id: str, redis_url: str):
    """Persist mode state to Redis with 1h TTL."""
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        await r.set(
            f"mode_state:{room_id}",
            json.dumps(_state_to_dict(state)),
            ex=3600,
        )
    finally:
        await r.aclose()


async def load_mode_state_from_redis(room_id: str, redis_url: str) -> ModeState | None:
    """Load mode state from Redis. Returns None if not found."""
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        raw = await r.get(f"mode_state:{room_id}")
        if raw:
            return _state_from_dict(json.loads(raw))
    finally:
        await r.aclose()
    return None
