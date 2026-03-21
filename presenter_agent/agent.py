"""Presenter Agent — joins LiveKit call, learns from instructor, conducts voice demo.

Uses livekit-agents 1.4.x API (Agent + AgentSession + function_tool).

Dual-mode agent:
  - STUDENT MODE (default): Watches the instructor's screen share (no Playwright).
    The Chrome extension captures clicks, scrolls, navigation, and input on the demo
    site for visit timeline tracking and learning context enrichment.
  - DEMO EXPERT MODE: Starts Playwright, shares the agent's own browser screen, and
    conducts a structured product demo following a roadmap. Auto-advances through
    steps via tool calls, with an 8s silence detector as safety net.
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
    APIConnectOptions,
    AutoSubscribe,
    JobContext,
    JobProcess,
    JobRequest,
    WorkerOptions,
    cli,
)
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import deepgram, silero, openai as livekit_openai
from livekit.plugins.turn_detector.multilingual import MultilingualModel
import redis.asyncio as aioredis

from backend.config import LLM_MODEL, FAST_DEMO
from presenter_agent.screen_share import BrowserScreenShare
from presenter_agent.instructor_capture import InstructorScreenCapture
from presenter_agent.visual_agent import VisualAgent
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
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.3,   # faster end-of-speech detection (default 0.55)
        activation_threshold=0.45,  # slightly more sensitive (default 0.5)
    )


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
    room_name = ctx.room.name
    is_console = room_name == "console"
    logger.info(f"Presenter agent connected to room: {room_name}")

    # Get website URL and optional login credentials from room metadata
    metadata = json.loads(ctx.room.metadata or "{}")
    url = metadata.get("url", "https://example.com")
    login_email = metadata.get("login_email")
    login_password = metadata.get("login_password")
    room_id = room_name
    logger.info(f"Demo URL: {url}")

    if is_console:
        # Console mode: text-only chat with instructions but no browser/Redis/tools
        instructions = build_student_instructions(url, None, [])
        console_llm = livekit_openai.LLM.with_openrouter(model=LLM_MODEL)
        console_llm._strict_tool_schema = False
        agent = Agent(
            instructions=instructions,
            llm=console_llm,
        )
        session = AgentSession()
        await session.start(agent=agent, room=ctx.room)
        await session.say(
            "Hey! I'm in console test mode — no browser or screen share, "
            "but I can chat with you about demo strategy. What would you like to work on?"
        )
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        return

    # --- Full mode (LiveKit room) ---

    # Fetch any existing research
    research = await get_research_context(room_id)
    log_event(logger, "research_context_received", "Fetched initial research context", {
        "room_id": room_id,
        "url": url,
        "research_status": research.get("status") if research else "none",
        "has_knowledge": bool(research and research.get("knowledge")),
        "has_demo_script": bool(research and research.get("demo_script")),
    })

    # Set up instructor screen capture (subscribes to instructor's screen share track)
    instructor_capture = InstructorScreenCapture()
    instructor_capture.attach_to_room(ctx.room)

    # Create BrowserScreenShare but do NOT start Playwright — deferred to demo mode switch
    screen_share = BrowserScreenShare()

    # Create ModeManager (agent/session not yet set — circular dep)
    mode_manager = ModeManager(
        screen_share, room_id, REDIS_URL, url, ctx.room,
        login_email=login_email, login_password=login_password,
    )

    # Get student mode tools and instructions
    tools = mode_manager.get_student_tools()
    instructions = build_student_instructions(url, research, [])

    # Build the agent (starts in Student Mode — sees instructor's screen, no Playwright)
    # Pipeline components (LLM, STT, TTS, VAD) go on the SESSION, not the agent.
    # This ensures AgentTask subtasks (used by TaskGroup in demo mode) can inherit
    # the pipeline via session fallback. If set only on the agent, subtasks get None.
    agent = VisualAgent(
        screen_share=screen_share,
        instructor_capture=instructor_capture,
        mode_manager=mode_manager,
        instructions=instructions,
        tools=tools,
    )

    # Create session with pipeline components — tasks inherit these via session fallback
    # Use reduced LLM retry/timeout to prevent cascading failures:
    # Default (max_retry=3, timeout=10s) = ~44s worst case, which causes LiveKit ping timeouts.
    # With max_retry=1, timeout=20s = ~40s worst case, keeps LiveKit alive while giving
    # Haiku via OpenRouter enough headroom for vision (screenshot) payloads.
    session_llm = livekit_openai.LLM.with_openrouter(model=LLM_MODEL)
    session_llm._strict_tool_schema = False
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-3", language="en"),
        llm=session_llm,
        tts=deepgram.TTS(),
        turn_detection=MultilingualModel(),
        max_tool_steps=5,  # allow highlight + scroll + highlight + move_mouse + step_complete in one response
        conn_options=SessionConnectOptions(
            llm_conn_options=APIConnectOptions(max_retry=1, timeout=20.0),
        ),
    )
    await session.start(
        agent=agent,
        room=ctx.room,
    )

    # Complete the circular dep — ModeManager now has access to live agent/session
    mode_manager.agent = agent
    mode_manager.session = session

    # Wire up silence detector activity tracking
    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev):
        # Record activity when agent starts speaking or thinking (tool calls)
        if ev.new_state in ("speaking", "thinking"):
            mode_manager.record_activity()

    @session.on("function_tools_executed")
    def _on_tools_executed(*args):
        mode_manager.record_activity()

    @session.on("user_state_changed")
    def _on_user_state_changed(ev):
        # Record activity when user starts speaking (prevents false silence triggers)
        if ev.new_state == "speaking":
            mode_manager.record_activity()

    log_event(logger, "session_started", f"Presenter session started for room {room_id}", {
        "room_id": room_id,
        "url": url,
        "mode": "fast_demo" if FAST_DEMO else "student",
    })

    if FAST_DEMO:
        # Fast demo mode: skip Student Mode, go straight to Demo Expert with existing roadmap
        from presenter_agent.roadmap_generator import load_roadmap_from_disk
        from presenter_agent.demo_task import create_demo_task_group

        existing_roadmap = load_roadmap_from_disk(url)
        if existing_roadmap is None:
            logger.error(f"FAST_DEMO enabled but no existing roadmap found for {url}")
            await session.say(
                "Fast demo mode is on but I couldn't find a previous roadmap for this site. "
                "Run a normal session first to generate one."
            )
        else:
            log_event(logger, "fast_demo_start", f"Starting fast demo with {len(existing_roadmap.steps)} steps", {
                "room_id": room_id,
                "url": url,
                "steps": len(existing_roadmap.steps),
            })

            await session.say("Starting the demo now!")

            async def run_fast_demo():
                """Background task: prepare browser and run TaskGroup."""
                try:
                    roadmap = await mode_manager.prepare_demo(existing_roadmap=existing_roadmap)
                    if roadmap is None:
                        logger.error("Fast demo: prepare_demo failed")
                        return

                    browser_tools = mode_manager.get_demo_step_tools()
                    chat_ctx = agent.chat_ctx

                    task_group = create_demo_task_group(
                        roadmap=roadmap,
                        browser_tools=browser_tools,
                        screen_share=mode_manager.screen_share,
                        url=url,
                        chat_ctx=chat_ctx,
                        room_id=room_id,
                        redis_url=REDIS_URL,
                    )
                    mode_manager.active_task_group = task_group

                    try:
                        await task_group
                    except Exception as e:
                        log_event(logger, "fast_demo_error", f"TaskGroup error: {e}", {
                            "room_id": room_id, "error": str(e),
                        })
                    finally:
                        mode_manager.active_task_group = None

                    await mode_manager.switch_to_student()
                    log_event(logger, "fast_demo_complete", "Fast demo finished", {"room_id": room_id})
                except Exception as e:
                    log_event(logger, "fast_demo_error", f"Fast demo failed: {e}", {
                        "room_id": room_id, "error": str(e),
                    })

            asyncio.create_task(run_fast_demo())
    else:
        # Normal flow: start in Student Mode
        mode_manager.start_nudge_detector()

        await session.say(
            "Hey! I'm ready to learn how to demo this product. "
            "Share your screen and start browsing the site — I'll watch "
            "and take notes on your approach. Teach me how you'd present it!"
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

    # Background task: listen for manual mode switch commands (from extension/API)
    async def monitor_mode_commands():
        try:
            r = aioredis.from_url(REDIS_URL, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"mode_commands:{room_id}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        cmd = json.loads(message["data"])
                        target_mode = cmd.get("mode")
                        current_mode = mode_manager.state.mode
                        if target_mode == current_mode:
                            log_event(logger, "mode_command_ignored", f"Already in {current_mode} mode", {
                                "room_id": room_id,
                            })
                            continue

                        if target_mode == "demo_expert":
                            result = await mode_manager.switch_to_demo()
                            log_event(logger, "mode_command_executed", f"Switched to demo_expert via command: {result}", {
                                "room_id": room_id,
                            })
                        elif target_mode == "student":
                            # Cancel active TaskGroup if running
                            if mode_manager.active_task_group and not mode_manager.active_task_group.done():
                                mode_manager.active_task_group.cancel()
                                mode_manager.active_task_group = None
                                log_event(logger, "task_group_cancelled", "Active TaskGroup cancelled by manual mode switch", {
                                    "room_id": room_id,
                                })
                            result = await mode_manager.switch_to_student()
                            log_event(logger, "mode_command_executed", f"Switched to student via command: {result}", {
                                "room_id": room_id,
                            })
                    except Exception as e:
                        log_event(logger, "mode_command_failed", f"Error processing mode command: {e}", {
                            "room_id": room_id,
                            "error": str(e),
                        }, level=logging.ERROR)
        except asyncio.CancelledError:
            pass

    mode_cmd_task = asyncio.create_task(monitor_mode_commands())

    # Background task: listen for extension events, track visit timeline
    async def monitor_extension_events():
        try:
            r = aioredis.from_url(REDIS_URL, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"instructor_events_stream:{room_id}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        event = json.loads(message["data"])
                        event_type = event.get("type")

                        # Track visit timeline on navigation events
                        if event_type == "navigation":
                            event_url = event.get("url", "")
                            mode_manager.state.track_navigation(event_url)

                            log_event(logger, "extension_navigation", f"Instructor navigated to {event_url}", {
                                "room_id": room_id,
                                "url": event_url,
                                "visit_count": len(mode_manager.state.visit_timeline),
                            })

                        # Add all events to current visit session
                        mode_manager.state.add_event_to_current_visit(event)

                    except Exception as e:
                        log_event(logger, "extension_event_error", f"Error processing extension event: {e}", {
                            "room_id": room_id,
                            "error": str(e),
                        }, level=logging.ERROR)
        except asyncio.CancelledError:
            pass

    extension_events_task = asyncio.create_task(monitor_extension_events())

    # Keep alive
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        mode_manager.stop_silence_detector()
        mode_manager.stop_nudge_detector()
        monitor_task.cancel()
        mode_cmd_task.cancel()
        extension_events_task.cancel()
        instructor_capture.stop()
        await screen_share.stop()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            request_fnc=request_fnc,
            prewarm_fnc=prewarm,
        ),
    )
