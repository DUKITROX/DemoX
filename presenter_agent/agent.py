"""Presenter Agent — joins LiveKit call, shares browser screen, conducts voice demo.

Uses livekit-agents 1.4.x API (Agent + AgentSession + function_tool).
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
from livekit.plugins import deepgram, silero, anthropic
import redis.asyncio as aioredis

from presenter_agent.screen_share import BrowserScreenShare
from presenter_agent.tools import create_demo_tools

from backend.json_logger import setup_json_logger, log_event

logger = setup_json_logger("presenter", "presenter.log")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


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


def build_instructions(url: str, research: dict | None) -> str:
    """Build lean agent instructions (~3KB) with navigation rules and page-guide workflow."""
    # Extract high-level info from research
    product_name = "this website"
    features_summary = ""
    demo_flow_summary = ""
    available_pages = []

    if research and research.get("status") == "complete":
        knowledge = research.get("knowledge", {})
        product_name = knowledge.get("product_name", "this website")

        # Compact features list
        features = knowledge.get("all_features", [])[:10]
        if features:
            features_summary = "Key features: " + ", ".join(features)

        # Extract demo step summaries (just step + narration, no selectors)
        demo_script_raw = research.get("demo_script", "")
        if demo_script_raw:
            try:
                script = json.loads(demo_script_raw) if isinstance(demo_script_raw, str) else demo_script_raw
                steps = script.get("demo_steps", [])
                step_lines = []
                for s in steps[:10]:
                    action = s.get("action", "")
                    narration = s.get("narration", "")
                    step_lines.append(f"  {s.get('step', '?')}. [{action}] {narration[:120]}")
                demo_flow_summary = "Demo flow outline:\n" + "\n".join(step_lines)
            except (json.JSONDecodeError, TypeError):
                pass

        # List available page wikis
        page_wikis = research.get("page_wikis", {})
        available_pages = list(page_wikis.keys())

    research_ready = research and research.get("status") == "complete"

    instructions = f"""You are an expert product demo specialist conducting a live demo of {product_name}: {url}
You are sharing your screen. The user sees everything you do.

=== CRITICAL NAVIGATION RULES ===
- You can ONLY navigate between pages by CLICKING visible elements (links, buttons, menu items).
- You do NOT have a navigate_to tool. All page transitions MUST happen via click_element.
- Use get_current_page_guide to see what's clickable — it scans the LIVE page.
- To go to a different page, find the right nav link text in your page guide and click it.

=== HOW TO CLICK ELEMENTS ===
- ALWAYS pass the element's VISIBLE TEXT to click_element.
- Example: click_element("Pricing") — NOT click_element("nav a:nth-child(3)")
- Example: click_element("Start Free Trial") — NOT click_element(".hero .btn-primary")
- The system automatically finds elements by role, text, and accessibility — CSS selectors are NOT needed.
- get_current_page_guide shows all clickable elements in quotes. Use the EXACT text from those quotes.

=== INTERACTION WORKFLOW ===
- ALWAYS call get_current_page_guide when you arrive on a new page (including the first page).
- The page guide gives you: talking points + a LIVE list of all navigation links, buttons, and other clickable elements.
- Speak naturally, 2-3 sentences max per turn.
- Use highlight_element to draw attention to elements (pass visible text, same as click_element).
- If click_element fails, call get_current_page_guide to refresh the element list, then try the exact text shown.
- If it still fails, narrate what you wanted to show and move on. Never retry more than once.

=== PRODUCT OVERVIEW ===
{features_summary if features_summary else "(Research still in progress — call get_current_page_guide and get_research_context for info)"}

{demo_flow_summary if demo_flow_summary else ""}

{"Available page guides: " + ", ".join(available_pages) if available_pages else ""}

{"" if research_ready else "Note: Research is still in progress. Use get_research_context periodically for updates."}
"""
    return instructions


async def entrypoint(ctx: JobContext):
    """Main agent entrypoint — called when dispatched to a room."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Presenter agent connected to room: {ctx.room.name}")

    # Get website URL from room metadata
    metadata = json.loads(ctx.room.metadata or "{}")
    url = metadata.get("url", "https://example.com")
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

    # Start browser and screen share
    screen_share = BrowserScreenShare()
    await screen_share.start(ctx.room, url)

    # Create tools
    tools = create_demo_tools(screen_share, room_id, REDIS_URL)

    # Build the agent
    instructions = build_instructions(url, research)

    agent = Agent(
        instructions=instructions,
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=anthropic.LLM(model="claude-haiku-4-5"),
        tts=deepgram.TTS(),
        tools=tools,
    )

    # Create session and start
    session = AgentSession()
    await session.start(
        agent=agent,
        room=ctx.room,
    )
    log_event(logger, "session_started", f"Presenter session started for room {room_id}", {
        "room_id": room_id,
        "url": url,
    })

    # Greet the user and trigger page guide fetch
    product_name = ""
    if research and research.get("knowledge", {}).get("product_name"):
        product_name = research["knowledge"]["product_name"]
        await session.say(
            f"Hello! Welcome to the demo of {product_name}. "
            "I'm sharing my screen so you can see the website. "
            "Let me check what's on this page and then walk you through the key features."
        )
    else:
        await session.say(
            "Hello! Welcome! I'm sharing my screen and I'll walk you through this website. "
            "Let me take a look at what's on this page and we'll get started. "
            "Feel free to ask me anything along the way!"
        )

    # Background task: monitor research updates and refresh instructions
    async def monitor_research():
        try:
            r = aioredis.from_url(REDIS_URL, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"research_updates:{room_id}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        new_research = json.loads(message["data"])
                        new_instructions = build_instructions(url, new_research)
                        await agent.update_instructions(new_instructions)
                        log_event(logger, "instructions_updated", "Updated agent instructions with new research", {
                            "room_id": room_id,
                            "research_status": new_research.get("status"),
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
        await screen_share.stop()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            request_fnc=request_fnc,
            prewarm_fnc=prewarm,
        ),
    )
