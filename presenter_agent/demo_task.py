"""DemoStepTask — each roadmap step runs as a focused AgentTask.

A TaskGroup sequences these tasks so the agent only sees ONE step at a time,
making tool calling trivial (same as responding to a direct user command).

Key optimization: on_enter() pre-navigates and injects a full page briefing
(screenshot + element list + research talking points) so the agent can narrate
and interact in 2-3 LLM turns instead of 6-8.
"""

import asyncio
import logging
import re

from livekit.agents import AgentTask, RunContext, function_tool, llm
from livekit.agents.llm.chat_context import FunctionCallOutput

from presenter_agent.mode_state import RoadmapStep, StructuredRoadmap
from presenter_agent.instructions import build_step_instructions
from presenter_agent.visual_agent import inject_screenshot_into_context, inject_step_briefing, _SCREENSHOT_TAG
from presenter_agent.tools import build_page_guide

logger = logging.getLogger(__name__)

# Tools that cause visual changes — only inject fresh screenshot after these
_VISUAL_CHANGE_TOOLS = {"click_element", "scroll_down", "scroll_to_element"}


def _parse_click_target(navigation_action: str | None) -> str | None:
    """Parse click_element("Pricing") → "Pricing". Returns None if no match."""
    if not navigation_action:
        return None
    m = re.search(r'click_element\(["\'](.+?)["\']\)', navigation_action)
    return m.group(1) if m else None


class DemoStepTask(AgentTask[bool]):
    """Executes a single roadmap step: navigate, narrate, interact, then complete.

    on_enter() handles navigation programmatically and injects a pre-built briefing.
    The agent just needs to narrate and do in-page interactions (2-3 LLM turns).
    Returns True on normal completion, False if aborted (user wants to stop).
    """

    def __init__(
        self,
        step: RoadmapStep,
        browser_tools: list,
        screen_share,
        url: str,
        room_id: str,
        redis_url: str,
    ):
        self._step = step
        self._screen_share = screen_share
        self._browser_tools = browser_tools
        self._room_id = room_id
        self._redis_url = redis_url
        self._nudge_task: asyncio.Task | None = None

        instructions = build_step_instructions(step, url)

        super().__init__(
            instructions=instructions,
            tools=[*browser_tools],
        )

    async def on_enter(self) -> None:
        """Pre-navigate, build page briefing, inject it, then kick off narration."""
        step = self._step

        # 1. Parse navigation target and execute click
        click_target = _parse_click_target(step.navigation_action)
        if click_target:
            try:
                await self._screen_share.click(click_target)
                await asyncio.sleep(0.8)  # Let SPA routing settle
                logger.info(f"Step '{step.id}': pre-navigated via click '{click_target}'")
            except Exception as e:
                logger.warning(f"Step '{step.id}': pre-navigation failed for '{click_target}': {e} — continuing on current page")

        # 2. Take screenshot
        screenshot = await self._screen_share.take_screenshot()

        # 3. Get current URL and build page guide
        current_url = await self._screen_share.get_current_url() or ""
        guide_text, _, _ = await build_page_guide(
            self._screen_share, self._room_id, self._redis_url, current_url,
        )

        # 4. Inject combined briefing into chat context
        if screenshot:
            chat_ctx = self.session.chat_ctx if self.session else None
            if chat_ctx:
                inject_step_briefing(chat_ctx, screenshot, guide_text, step.title)
                logger.info(f"Step '{step.id}': injected briefing (screenshot + guide)")

        # 5. Kick off narration
        kickoff = (
            f"Execute step: '{step.title}'. Follow your step instructions. Call step_complete() when done."
        )
        self.session.generate_reply(instructions=kickoff)

        # 6. Start safety nudge
        self._nudge_task = asyncio.create_task(self._nudge_loop())

    async def _nudge_loop(self):
        """Re-kick the agent if it goes silent without calling step_complete."""
        try:
            # First nudge at 12s
            await asyncio.sleep(12.0)
            if not self.done():
                logger.info(f"Nudging step '{self._step.id}' — agent went silent (1st)")
                # Inject fresh screenshot with nudge
                await self._inject_fresh_screenshot()
                self.session.generate_reply(
                    instructions=(
                        "Continue presenting this section. Pick up where you left off — "
                        "narrate what you see on screen, do any remaining actions, then call step_complete()."
                    )
                )
                # Second nudge 10s after first (total ~22s)
                await asyncio.sleep(10.0)
                if not self.done():
                    logger.info(f"Nudging step '{self._step.id}' — agent went silent (2nd)")
                    self.session.generate_reply(
                        instructions=(
                            "Wrap up this section now. Summarize what you showed and call step_complete()."
                        )
                    )
                    # Force-complete 8s after second nudge (total ~30s)
                    await asyncio.sleep(8.0)
                    if not self.done():
                        logger.warning(f"Step '{self._step.id}' still incomplete after 2 nudges, force-completing")
                        try:
                            self.complete(True)
                        except RuntimeError:
                            pass  # Already completed by agent between check and call
        except asyncio.CancelledError:
            pass

    async def _inject_fresh_screenshot(self):
        """Take and inject a fresh screenshot into context."""
        screenshot = await self._screen_share.take_screenshot()
        if screenshot is None:
            return
        chat_ctx = self.session.chat_ctx if self.session else None
        if chat_ctx:
            inject_screenshot_into_context(
                chat_ctx,
                screenshot,
                "[Updated browser screen after your actions.]",
                f"[Continue step: {self._step.title}. Call step_complete() when done.]",
            )

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        """Only inject a fresh screenshot if a visual-change tool was recently executed."""
        # Scan recent items for FunctionCallOutput from visual-change tools
        has_visual_change = False
        for item in reversed(turn_ctx.items[-10:]):
            if isinstance(item, FunctionCallOutput) and item.name in _VISUAL_CHANGE_TOOLS:
                has_visual_change = True
                break
            # Stop at the last screenshot — only care about tools since then
            if isinstance(item, llm.ChatMessage) and item.extra.get(_SCREENSHOT_TAG):
                break

        if not has_visual_change:
            return

        screenshot = await self._screen_share.take_screenshot()
        if screenshot is None:
            return

        inject_screenshot_into_context(
            turn_ctx,
            screenshot,
            "[This is your current browser screen after your action.]",
            f"[You are executing step: {self._step.title}. Continue following the step instructions, then call step_complete() when done.]",
        )
        logger.debug(f"Injected post-action screenshot for step '{self._step.id}'")

    @function_tool(description="Call this when you have finished all actions and narration for the current demo step. This signals that you're ready to move to the next section.")
    async def step_complete(self, context: RunContext) -> None:
        if self.done():
            return
        logger.info(f"Step '{self._step.id}' completed")
        if self._nudge_task:
            self._nudge_task.cancel()
        self.complete(True)

    @function_tool(description="Call this if the user wants to stop the demo and go back to learning mode. Only use when the user explicitly asks to stop.")
    async def abort_demo(self, context: RunContext) -> None:
        if self.done():
            return
        logger.info(f"Demo aborted at step '{self._step.id}'")
        if self._nudge_task:
            self._nudge_task.cancel()
        self.complete(False)


class DemoOpeningTask(AgentTask[bool]):
    """Delivers the opening line before the first step."""

    def __init__(self, opening_line: str, url: str, screen_share):
        self._opening_line = opening_line
        self._screen_share = screen_share
        self._nudge_task: asyncio.Task | None = None

        super().__init__(
            instructions=(
                f"You are an expert product demo specialist about to demo {url}. "
                "Your screen is shared. Deliver your opening greeting naturally."
            ),
        )

    async def on_enter(self) -> None:
        # Inject screenshot so agent has visual context for the opening
        screenshot = await self._screen_share.take_screenshot()
        if screenshot:
            chat_ctx = self.session.chat_ctx if self.session else None
            if chat_ctx:
                inject_screenshot_into_context(
                    chat_ctx,
                    screenshot,
                    "[This is your browser screen. The demo is about to begin.]",
                )

        self.session.generate_reply(
            instructions=(
                f"Say this opening naturally (paraphrase slightly): \"{self._opening_line}\" "
                "Then call step_complete() to proceed to the first demo section."
            ),
        )
        self._nudge_task = asyncio.create_task(self._nudge_loop())

    async def _nudge_loop(self):
        """Re-kick the agent if it goes silent without calling step_complete."""
        try:
            await asyncio.sleep(10.0)
            if not self.done():
                logger.info("Nudging opening task — agent went silent")
                self.session.generate_reply(
                    instructions=(
                        "You went quiet. Deliver your opening greeting and then "
                        "call step_complete() to start the demo."
                    )
                )
                await asyncio.sleep(10.0)
                if not self.done():
                    logger.warning("Opening task still incomplete after 2 nudges, force-completing")
                    try:
                        self.complete(True)
                    except RuntimeError:
                        pass  # Already completed by agent between check and call
        except asyncio.CancelledError:
            pass

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        screenshot = await self._screen_share.take_screenshot()
        if screenshot is None:
            return
        inject_screenshot_into_context(
            turn_ctx,
            screenshot,
            "[This is your current browser screen. The demo is about to begin.]",
        )

    @function_tool(description="Call this after delivering the opening greeting to proceed to the demo.")
    async def step_complete(self, context: RunContext) -> None:
        if self.done():
            return
        if self._nudge_task:
            self._nudge_task.cancel()
        self.complete(True)

    @function_tool(description="Call this if the user wants to stop before the demo begins.")
    async def abort_demo(self, context: RunContext) -> None:
        if self.done():
            return
        if self._nudge_task:
            self._nudge_task.cancel()
        self.complete(False)


class DemoClosingTask(AgentTask[bool]):
    """Delivers the closing line after all steps."""

    def __init__(self, closing_line: str, url: str, screen_share):
        self._closing_line = closing_line
        self._screen_share = screen_share
        self._nudge_task: asyncio.Task | None = None

        super().__init__(
            instructions=(
                f"You just finished demoing {url}. "
                "Deliver your closing message and ask if there are questions."
            ),
        )

    async def on_enter(self) -> None:
        # Inject screenshot so agent has visual context for the closing
        screenshot = await self._screen_share.take_screenshot()
        if screenshot:
            chat_ctx = self.session.chat_ctx if self.session else None
            if chat_ctx:
                inject_screenshot_into_context(
                    chat_ctx,
                    screenshot,
                    "[This is your browser screen. The demo is wrapping up.]",
                )

        self.session.generate_reply(
            instructions=(
                f"Say this closing naturally (paraphrase slightly): \"{self._closing_line}\" "
                "Then call step_complete()."
            ),
        )
        self._nudge_task = asyncio.create_task(self._nudge_loop())

    async def _nudge_loop(self):
        """Re-kick the agent if it goes silent without calling step_complete."""
        try:
            await asyncio.sleep(10.0)
            if not self.done():
                logger.info("Nudging closing task — agent went silent")
                self.session.generate_reply(
                    instructions=(
                        "You went quiet. Deliver your closing message and then "
                        "call step_complete() to finish the demo."
                    )
                )
                await asyncio.sleep(10.0)
                if not self.done():
                    logger.warning("Closing task still incomplete after 2 nudges, force-completing")
                    try:
                        self.complete(True)
                    except RuntimeError:
                        pass  # Already completed by agent between check and call
        except asyncio.CancelledError:
            pass

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        screenshot = await self._screen_share.take_screenshot()
        if screenshot is None:
            return
        inject_screenshot_into_context(
            turn_ctx,
            screenshot,
            "[This is your browser screen. The demo is wrapping up.]",
        )

    @function_tool(description="Call this after delivering the closing message.")
    async def step_complete(self, context: RunContext) -> None:
        if self.done():
            return
        if self._nudge_task:
            self._nudge_task.cancel()
        self.complete(True)

    @function_tool(description="Call this if the user wants to switch back to learning mode.")
    async def abort_demo(self, context: RunContext) -> None:
        if self.done():
            return
        if self._nudge_task:
            self._nudge_task.cancel()
        self.complete(False)


def create_demo_task_group(
    roadmap: StructuredRoadmap,
    browser_tools: list,
    screen_share,
    url: str,
    chat_ctx: llm.ChatContext,
    room_id: str,
    redis_url: str,
) -> "TaskGroup":
    """Create a TaskGroup that sequences all roadmap steps.

    Each step is a DemoStepTask with focused instructions for just that section.
    The TaskGroup handles progression — when one task calls step_complete(),
    the framework moves to the next.
    """
    from livekit.agents.beta.workflows import TaskGroup

    task_group = TaskGroup(
        chat_ctx=chat_ctx,
        summarize_chat_ctx=False,  # Don't summarize — we switch back to student mode after
    )

    # Opening
    task_group.add(
        lambda: DemoOpeningTask(roadmap.opening_line, url, screen_share),
        id="opening",
        description="Opening greeting for the demo",
    )

    # Each roadmap step
    for step in roadmap.steps:
        # Capture step in closure
        _step = step
        task_group.add(
            lambda s=_step: DemoStepTask(
                s, browser_tools, screen_share, url, room_id, redis_url,
            ),
            id=step.id,
            description=step.title,
        )

    # Closing
    task_group.add(
        lambda: DemoClosingTask(roadmap.closing_line, url, screen_share),
        id="closing",
        description="Closing message and Q&A",
    )

    return task_group
