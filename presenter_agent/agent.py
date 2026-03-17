"""Presenter Agent — joins LiveKit call, watches instructor, conducts voice demo.

Uses livekit-agents 1.4.x API (Agent + AgentSession + function_tool).

Dual-mode agent:
  - STUDENT MODE (default): Watches the instructor's screen share and learns how
    they demo the product. Uses vision analysis (Claude Haiku) to detect which page
    the instructor is showing, and mirrors it in a background Playwright browser
    for full DOM access. Researcher crawls in background.
  - DEMO EXPERT MODE: Once the agent has gathered enough knowledge, it switches to
    sharing its own Playwright browser screen and conducting a structured product
    demo following a self-generated roadmap.
  Users can ask the agent to switch back to student mode at any time.
"""

import asyncio
import json
import logging
import os

from dotenv import load_dotenv
load_dotenv()

from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    JobRequest,
    WorkerOptions,
    cli,
)
from livekit.plugins import deepgram, silero, openai as livekit_openai
import redis.asyncio as aioredis

from presenter_agent.screen_share import BrowserScreenShare
from presenter_agent.instructor_watcher import InstructorScreenWatcher
from presenter_agent.mode_manager import ModeManager
from presenter_agent.instructions import build_student_instructions

from backend.json_logger import setup_json_logger, log_event

logger = setup_json_logger("presenter", "presenter.log")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


class AgentState:
    """Shared mutable state accessible by both the agent entrypoint and tools."""

    def __init__(self):
        self.mode: str = "student"  # "student" or "demo_expert"
        self.agent: Agent | None = None
        self.session: AgentSession | None = None
        self.url: str = ""
        self.room_id: str = ""
        self.research: dict | None = None
        self.demo_roadmap: list[dict] | None = None  # built when switching to demo mode


async def request_fnc(req: JobRequest):
    """Accept job requests with a fixed identity so the frontend can find us."""
    await req.accept(
        identity="presenter-agent",
        name="Demo Agent",
    )


def prewarm(proc: JobProcess):
    """Pre-load VAD model for faster startup."""
    proc.userdata["vad"] = silero.VAD.load()


async def get_research_context(room_id: str) -> dict | None:
    """Fetch research data from Redis."""
    try:
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        raw = await r.get(f"research:{room_id}")
        await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"Could not fetch research: {e}")
    return None


async def entrypoint(ctx: JobContext):
    """Main agent entrypoint — called when dispatched to a room."""
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
    logger.info(f"Presenter agent connected to room: {ctx.room.name}")

    # Get website URL and optional login credentials from room metadata
    metadata = json.loads(ctx.room.metadata or "{}")
    url = metadata.get("url", "https://example.com")
    login_email = metadata.get("login_email")
    login_password = metadata.get("login_password")
    room_id = ctx.room.name
    logger.info(f"Demo URL: {url}")

    # Fetch any existing research
    research = await get_research_context(room_id)
    log_event(logger, "research_context_received", "Fetched initial research context", {
        "room_id": room_id,
        "url": url,
        "research_status": research.get("status") if research else "none",
        "has_knowledge": bool(research and research.get("knowledge")),
        "has_demo_script": bool(research and research.get("demo_script")),
    })

    # Start browser (but don't publish screen share — instructor shares theirs in Student Mode)
    screen_share = BrowserScreenShare()
    await screen_share.start_browser(url, login_email=login_email, login_password=login_password)

    # Start watching instructor's screen share for page detection
    watcher = InstructorScreenWatcher(ctx.room, screen_share, url)
    await watcher.start()

    # Create ModeManager (agent/session not yet set — circular dep)
    mode_manager = ModeManager(screen_share, watcher, room_id, REDIS_URL, url, ctx.room)

    # Get student mode tools and instructions
    tools = mode_manager.get_student_tools()
    instructions = build_student_instructions(url, research, [])

    # Build the agent (starts in Student Mode)
    agent = Agent(
        instructions=instructions,
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=livekit_openai.LLM(
            model="google/gemini-3.1-flash-lite-preview",
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        ),
        tts=deepgram.TTS(),
        tools=tools,
    )

    # Create session and start
    session = AgentSession()
    await session.start(
        agent=agent,
        room=ctx.room,
    )

    # Complete the circular dep — ModeManager now has access to live agent/session
    mode_manager.agent = agent
    mode_manager.session = session

    log_event(logger, "session_started", f"Presenter session started in student mode for room {room_id}", {
        "room_id": room_id,
        "url": url,
        "mode": "student",
    })

    # Greet the user in student voice
    await session.say(
        "Hey! I'm ready to learn how to demo this product. "
        "Go ahead and share your screen — I'll watch how you present it "
        "and take notes on your approach."
    )

    # Background task: monitor research updates and refresh instructions (mode-aware)
    async def monitor_research():
        try:
            r = aioredis.from_url(REDIS_URL, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"research_updates:{room_id}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        new_research = json.loads(message["data"])
                        new_instructions = await mode_manager.rebuild_instructions(new_research)
                        await agent.update_instructions(new_instructions)
                        log_event(logger, "instructions_updated", "Updated agent instructions with new research", {
                            "room_id": room_id,
                            "research_status": new_research.get("status"),
                            "mode": mode_manager.state.mode,
                            "instruction_length": len(new_instructions),
                        })
                    except Exception as e:
                        log_event(logger, "instruction_update_failed", f"Error processing research update: {e}", {
                            "room_id": room_id,
                            "error": str(e),
                        }, level=logging.ERROR)
        except asyncio.CancelledError:
            pass

    monitor_task = asyncio.create_task(monitor_research())

    # Keep alive
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        monitor_task.cancel()
        await watcher.stop()
        await screen_share.stop()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            request_fnc=request_fnc,
            prewarm_fnc=prewarm,
        ),
    )
