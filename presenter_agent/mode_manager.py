"""ModeManager — orchestrates mode switching for the presenter agent."""

import asyncio
import json
import logging
import time as time_mod

import redis.asyncio as aioredis

from presenter_agent.mode_state import (
    ModeState,
    StructuredRoadmap,
    save_mode_state_to_redis,
)
from presenter_agent.instructions import (
    build_student_instructions,
    build_demo_expert_instructions,
)
from presenter_agent.roadmap_generator import generate_roadmap
from presenter_agent.tools import (
    create_browser_tools,
    create_student_tools,
    make_save_learning_tool,
    make_remove_learning_tool,
    make_switch_to_demo_tool,
    make_switch_to_student_tool,
)

logger = logging.getLogger(__name__)


class ModeManager:
    """Orchestrates mode switching between Student and Demo Expert modes.

    Holds references to agent/session (set after construction to break circular dep)
    and manages state, instructions, and tool updates.
    """

    def __init__(self, screen_share, room_id: str, redis_url: str, url: str, room=None,
                 login_email: str | None = None, login_password: str | None = None):
        self.screen_share = screen_share
        self.room = room        # rtc.Room — needed for start_publishing()
        self.room_id = room_id
        self.redis_url = redis_url
        self.url = url
        self.agent = None       # set after Agent() creation
        self.session = None     # set after AgentSession() creation
        self.state = ModeState()

        # Login credentials — stored for deferred Playwright start in demo mode
        self._login_email = login_email
        self._login_password = login_password

        # Student tools (no browser needed)
        self._student_base_tools = create_student_tools(room_id, redis_url)
        # Browser tools created on-demand when Playwright starts
        self._browser_tools: list | None = None

        # Active TaskGroup reference — set during demo, used for cancellation
        self.active_task_group = None

        # Silence detector state
        self._silence_task: asyncio.Task | None = None
        self._last_activity_time: float = 0.0
        self._demo_complete: bool = False
        self._recovery_in_progress: bool = False

        # Note-taking nudge state
        self._nudge_task: asyncio.Task | None = None
        self._last_save_learning_time: float = 0.0

    async def _get_research(self) -> dict | None:
        """Fetch current research data from Redis."""
        try:
            r = aioredis.from_url(self.redis_url, decode_responses=True)
            raw = await r.get(f"research:{self.room_id}")
            await r.aclose()
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"Could not fetch research: {e}")
        return None

    def get_student_tools(self) -> list:
        """Return tools for Student Mode: research tools + save/remove learning + switch to demo.

        No browser tools — the agent sees the instructor's screen share directly.
        """
        return [
            *self._student_base_tools,
            make_save_learning_tool(self),
            make_remove_learning_tool(self),
            make_switch_to_demo_tool(self),
        ]

    def get_demo_expert_tools(self) -> list:
        """Return tools for Demo Expert Mode: browser tools + switch to student.

        Browser tools are created on-demand (Playwright must be started first).
        NOTE: This is kept for backward compat / manual mode switch. The TaskGroup
        flow uses get_demo_browser_tools() instead (no switch tool — tasks handle it).
        """
        if self._browser_tools is None:
            self._browser_tools = create_browser_tools(
                self.screen_share, self.room_id, self.redis_url,
                on_tool_activity=self.record_activity,
            )
        return [
            *self._browser_tools,
            make_switch_to_student_tool(self),
        ]

    def get_demo_browser_tools(self) -> list:
        """Return just the browser interaction tools (no mode switch tools).

        Used by DemoStepTask — each task has its own step_complete/abort_demo tools.
        """
        if self._browser_tools is None:
            self._browser_tools = create_browser_tools(
                self.screen_share, self.room_id, self.redis_url,
                on_tool_activity=self.record_activity,
            )
        return list(self._browser_tools)

    def get_demo_step_tools(self) -> list:
        """Return reduced tool set for demo steps (no page guide or research tools).

        Navigation and page guide are handled by on_enter() — the agent only needs
        in-page interaction tools: highlight, scroll, hover, move_mouse, click (for
        tabs/accordions), type_text.
        """
        if self._browser_tools is None:
            self._browser_tools = create_browser_tools(
                self.screen_share, self.room_id, self.redis_url,
                on_tool_activity=self.record_activity,
            )
        # Filter to in-page interaction tools only
        STEP_TOOL_NAMES = {
            "highlight_element", "scroll_down", "scroll_to_element",
            "hover_element", "move_mouse", "click_element", "type_text",
        }
        return [t for t in self._browser_tools if t.info.name in STEP_TOOL_NAMES]

    async def prepare_demo(self, existing_roadmap: StructuredRoadmap | None = None) -> StructuredRoadmap | None:
        """Prepare for demo mode: start Playwright, generate roadmap, start publishing.

        Does NOT update agent instructions/tools — the TaskGroup handles that per-step.
        If existing_roadmap is provided, skip roadmap generation (fast demo mode).
        Returns the StructuredRoadmap, or None on failure.
        """
        # 1. Stop note-taking nudge
        self.stop_nudge_detector()

        # 2. Close current visit session
        if self.state.visit_timeline:
            import time
            current = self.state.visit_timeline[-1]
            if current.end_time == 0.0:
                current.end_time = time.time()

        # 3. Start Playwright browser
        try:
            await self.screen_share.start_browser(
                self.url,
                login_email=self._login_email,
                login_password=self._login_password,
            )
            logger.info("Playwright browser started for demo mode")
        except Exception as e:
            logger.error(f"Failed to start Playwright browser: {e}")
            return None

        # 4. Generate structured roadmap from notes file (or use existing)
        roadmap = existing_roadmap or await generate_roadmap(self.url)

        # 5. Update state
        self.state.mode = "demo_expert"
        self._browser_tools = None  # Force recreation with fresh screen_share

        # 6. Persist state
        await save_mode_state_to_redis(self.state, self.room_id, self.redis_url)

        # 7. Navigate to home page and start publishing
        try:
            await self.screen_share.navigate(self.url)
        except Exception as e:
            logger.warning(f"Could not navigate to home for demo start: {e}")

        if self.room:
            try:
                await self.screen_share.start_publishing(self.room)
            except Exception as e:
                logger.warning(f"Could not start publishing screen share: {e}")

        return roadmap

    async def switch_to_demo(self) -> str:
        """Switch from Student to Demo Expert mode (legacy path for manual mode switch).

        For the normal flow, use prepare_demo() + TaskGroup instead.
        This is kept for manual mode switch via API/extension.
        """
        roadmap = await self.prepare_demo()
        if roadmap is None:
            return "Could not start browser for demo."

        # For manual switch, use the old approach with full instructions
        from presenter_agent.mode_state import DemoRoadmap
        from presenter_agent.roadmap_generator import _roadmap_to_readable

        # Create a legacy DemoRoadmap for build_demo_expert_instructions
        markdown = _roadmap_to_readable(roadmap)
        legacy_roadmap = DemoRoadmap(markdown_content=markdown, file_path=roadmap.file_path)
        self.state.roadmap = legacy_roadmap

        research = await self._get_research()
        new_instructions = build_demo_expert_instructions(
            self.url, research, legacy_roadmap,
        )
        new_tools = self.get_demo_expert_tools()

        if self.agent:
            await self.agent.update_instructions(new_instructions)
            await self.agent.update_tools(new_tools)

        await save_mode_state_to_redis(self.state, self.room_id, self.redis_url)

        if self.session:
            self.record_activity()
            self.session.generate_reply(
                instructions=(
                    "You just switched to demo expert mode. Your screen is now shared. "
                    "Start from the top of your demo script — say your Opening, call "
                    "get_current_page_guide, and begin executing step by step. "
                    "Keep going without stopping."
                ),
            )
            self.start_silence_detector()

        return "Mode switched to Demo Expert! Your demo script is ready. Starting the demo now."

    async def switch_to_student(self) -> str:
        """Switch from Demo Expert back to Student mode.

        Stops publishing, closes Playwright browser, resumes instructor screen capture.
        Updates instructions and tools. Sets feedback flag.
        Returns a prompt string for the tool response.
        """
        # 0. Stop silence detector and cancel any active TaskGroup
        self.stop_silence_detector()
        if self.active_task_group and not self.active_task_group.done():
            self.active_task_group.cancel()
            self.active_task_group = None

        # 1. Stop publishing and close Playwright browser entirely
        await self.screen_share.stop()
        self._browser_tools = None  # Invalidate browser tools

        # 2. Update state
        self.state.mode = "student"
        self.state.demo_feedback_requested = True

        # 3. Build new instructions and tools
        research = await self._get_research()
        new_instructions = build_student_instructions(
            self.url, research, self.state.learnings,
        )
        new_tools = self.get_student_tools()

        # 4. Update the live agent
        if self.agent:
            await self.agent.update_instructions(new_instructions)
            await self.agent.update_tools(new_tools)

        # 5. Persist state
        await save_mode_state_to_redis(self.state, self.room_id, self.redis_url)

        # 6. Start note-taking nudge
        self.start_nudge_detector()

        return (
            "Switched back to student mode. "
            "Ask the boss for feedback on your demo performance before continuing to learn."
        )

    async def rebuild_instructions(self, research: dict | None) -> str:
        """Rebuild instructions for the current mode (called when research updates arrive)."""
        if self.state.mode == "student":
            return build_student_instructions(
                self.url, research, self.state.learnings,
            )
        else:
            return build_demo_expert_instructions(
                self.url, research, self.state.roadmap,
            )

    # ── Silence Detector ──────────────────────────────────────────────

    def record_activity(self):
        """Reset the silence timer. Call when agent speaks, tool is called, or user speaks."""
        self._last_activity_time = time_mod.time()
        self._recovery_in_progress = False

    def start_silence_detector(self):
        """Start the background silence detector for demo mode."""
        self.stop_silence_detector()
        self._demo_complete = False
        self._last_activity_time = time_mod.time()
        self._silence_task = asyncio.create_task(self._silence_detector_loop())
        logger.info(f"Silence detector started for room {self.room_id}")

    def stop_silence_detector(self):
        """Stop the background silence detector."""
        if self._silence_task and not self._silence_task.done():
            self._silence_task.cancel()
            self._silence_task = None
            logger.info(f"Silence detector stopped for room {self.room_id}")

    async def _silence_detector_loop(self):
        """Monitor for 20s of agent silence and trigger recovery if needed."""
        SILENCE_THRESHOLD = 20.0

        try:
            while not self._demo_complete:
                await asyncio.sleep(1.0)

                if self.state.mode != "demo_expert":
                    break

                # Skip if a recovery is already in progress
                if self._recovery_in_progress:
                    continue

                elapsed = time_mod.time() - self._last_activity_time
                if elapsed < SILENCE_THRESHOLD:
                    continue

                logger.warning(
                    f"Silence detected ({elapsed:.1f}s) in room {self.room_id}"
                )

                # Recovery flow
                await self._recover_from_silence()

                # Reset timer to avoid re-triggering immediately
                self.record_activity()

        except asyncio.CancelledError:
            pass

    async def _recover_from_silence(self):
        """Recovery flow: say filler → generate_reply with retry instructions."""
        if not self.session:
            return

        # Guard against stacking multiple recovery calls
        if self._recovery_in_progress:
            return
        self._recovery_in_progress = True

        # 1. Say filler to keep listener informed
        self.session.say(
            "Give me just a second, I'm figuring some things out.",
            allow_interruptions=True,
        )

        # 2. Take a screenshot to see current state
        screenshot_context = ""
        try:
            screenshot_bytes = await self.screen_share.take_screenshot()
            if screenshot_bytes:
                screenshot_context = (
                    "A screenshot of your current browser screen is in the conversation context. "
                    "Use it to understand what's on screen right now. "
                )
        except Exception as e:
            logger.warning(f"Screenshot failed during recovery: {e}")

        retry_instructions = (
            f"You went silent for a bit. {screenshot_context}"
            "Look at your screenshot and your demo script. "
            "Continue from where you left off — call get_current_page_guide to see "
            "what's on the page, then keep executing your demo script. "
            "If you've finished all steps, say your closing line and ask if there are questions."
        )

        self.session.generate_reply(instructions=retry_instructions)

        # Reset flag — generate_reply is fire-and-forget, recovery attempt is complete
        self._recovery_in_progress = False

    # ── Note-Taking Nudge ─────────────────────────────────────────────

    def record_save_learning(self):
        """Record that save_learning was just called. Resets the nudge timer."""
        self._last_save_learning_time = time_mod.time()

    def start_nudge_detector(self):
        """Start the background nudge detector for student mode."""
        self.stop_nudge_detector()
        self._last_save_learning_time = time_mod.time()
        self._nudge_task = asyncio.create_task(self._nudge_detector_loop())
        logger.info(f"Note-taking nudge started for room {self.room_id}")

    def stop_nudge_detector(self):
        """Stop the background nudge detector."""
        if self._nudge_task and not self._nudge_task.done():
            self._nudge_task.cancel()
            self._nudge_task = None

    async def _nudge_detector_loop(self):
        """If 60+ seconds pass without a save_learning in student mode, nudge the agent."""
        NUDGE_THRESHOLD = 60.0

        try:
            while True:
                await asyncio.sleep(5.0)

                if self.state.mode != "student":
                    break

                elapsed = time_mod.time() - self._last_save_learning_time
                if elapsed < NUDGE_THRESHOLD:
                    continue

                # Only nudge if we have some visit activity (instructor is browsing)
                if not self.state.visit_timeline:
                    continue

                logger.info(f"Nudging agent to take notes ({elapsed:.0f}s since last save)")

                if self.session:
                    self.session.generate_reply(
                        instructions=(
                            "You haven't taken notes in a while. If the instructor has "
                            "shown you anything new or shared any insights, capture it "
                            "with save_learning now. Good notes make for a great demo later."
                        ),
                    )

                # Reset timer so we don't spam
                self._last_save_learning_time = time_mod.time()

        except asyncio.CancelledError:
            pass
