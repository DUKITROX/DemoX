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
    recent_events: list[dict] = field(default_factory=list)  # last 15s of extension events


@dataclass
class VisitSession:
    """A single visit to a page — separated by navigation away and back."""
    page_url: str
    visit_index: int  # 1st, 2nd, etc. visit to this page
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    events: list[dict] = field(default_factory=list)
    learning_topics: list[str] = field(default_factory=list)
    intent: str | None = None  # "primary"|"additional"|"contrast" — set by LLM at synthesis
    screenshot_b64: str | None = None  # base64-encoded screenshot captured on navigation


@dataclass
class RoadmapStep:
    id: str                          # e.g. "pricing_page"
    title: str                       # e.g. "Pricing Page Demo"
    instructions: str                # Focused narration + interaction for THIS step only
    navigation_action: str | None    # How to get here from previous step, e.g. "click Pricing"


@dataclass
class StructuredRoadmap:
    steps: list[RoadmapStep]
    opening_line: str
    closing_line: str
    file_path: str


@dataclass
class DemoRoadmap:
    markdown_content: str  # Full markdown demo script
    file_path: str         # Path on disk


@dataclass
class ModeState:
    mode: Literal["student", "demo_expert"] = "student"
    learnings: list[Learning] = field(default_factory=list)
    visit_timeline: list[VisitSession] = field(default_factory=list)
    roadmap: DemoRoadmap | None = None
    demo_feedback_requested: bool = False
    event_watermark: float = 0.0  # timestamp of last event consumed by save_learning

    def upsert_learning(self, topic: str, details: str, page_url: str,
                        recent_events: list[dict] | None = None) -> bool:
        """Insert or update a learning by topic. Returns True if updated, False if inserted."""
        topic_lower = topic.lower()
        for i, l in enumerate(self.learnings):
            if l.topic.lower() == topic_lower:
                self.learnings[i] = Learning(
                    topic=topic, details=details,
                    page_url=page_url, timestamp=time.time(),
                    recent_events=recent_events or [],
                )
                return True
        self.learnings.append(Learning(
            topic=topic, details=details,
            page_url=page_url, timestamp=time.time(),
            recent_events=recent_events or [],
        ))
        return False

    def remove_learning(self, topic: str) -> int:
        """Remove all learnings matching topic (case-insensitive). Returns count removed."""
        topic_lower = topic.lower()
        before = len(self.learnings)
        self.learnings = [l for l in self.learnings if l.topic.lower() != topic_lower]
        return before - len(self.learnings)

    def track_navigation(self, page_url: str) -> VisitSession:
        """Called when the instructor navigates to a new page. Closes current visit, opens new one."""
        now = time.time()

        # Close current visit if one exists
        if self.visit_timeline:
            current = self.visit_timeline[-1]
            if current.end_time == 0.0:
                current.end_time = now

        # Count how many times we've visited this URL
        visit_count = sum(1 for v in self.visit_timeline
                         if v.page_url == page_url) + 1

        visit = VisitSession(
            page_url=page_url,
            visit_index=visit_count,
            start_time=now,
        )
        self.visit_timeline.append(visit)
        return visit

    def add_event_to_current_visit(self, event: dict):
        """Append an extension event to the current (most recent) visit session."""
        if self.visit_timeline:
            self.visit_timeline[-1].events.append(event)

    def link_learning_to_current_visit(self, topic: str):
        """Record that a learning was saved during the current visit."""
        if self.visit_timeline:
            self.visit_timeline[-1].learning_topics.append(topic)


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
        "visit_timeline": [asdict(v) for v in state.visit_timeline],
        "demo_feedback_requested": state.demo_feedback_requested,
        "event_watermark": state.event_watermark,
    }
    if state.roadmap:
        d["roadmap"] = asdict(state.roadmap)
    return d


def _state_from_dict(d: dict) -> ModeState:
    """Deserialize ModeState from a dict."""
    state = ModeState(mode=d.get("mode", "student"))
    state.demo_feedback_requested = d.get("demo_feedback_requested", False)
    state.event_watermark = d.get("event_watermark", 0.0)
    for ld in d.get("learnings", []):
        # Handle backward compat: old learnings without recent_events
        if "recent_events" not in ld:
            ld["recent_events"] = []
        state.learnings.append(Learning(**ld))
    for vd in d.get("visit_timeline", []):
        # Handle backward compat: old visits without screenshot_b64
        if "screenshot_b64" not in vd:
            vd["screenshot_b64"] = None
        state.visit_timeline.append(VisitSession(**vd))
    rd = d.get("roadmap")
    if rd:
        # Handle backward compat: old format with steps/opening_line/closing_line
        if "markdown_content" not in rd:
            rd = {"markdown_content": "", "file_path": ""}
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
