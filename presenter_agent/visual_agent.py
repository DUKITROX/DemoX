"""VisualAgent — Agent subclass that injects a screenshot before each LLM turn.

In Student Mode, captures from the instructor's screen share track.
In Demo Expert Mode, captures from the agent's own Playwright browser.
"""

import base64
import logging

from livekit.agents import Agent, llm

from presenter_agent.screen_share import BrowserScreenShare
from presenter_agent.instructor_capture import InstructorScreenCapture

logger = logging.getLogger(__name__)

_SCREENSHOT_TAG = "is_screenshot"


def inject_screenshot_into_context(
    turn_ctx: llm.ChatContext,
    screenshot: bytes,
    context_text: str,
    reminder_text: str | None = None,
) -> None:
    """Inject a screenshot into the turn context, removing any previous screenshot.

    Shared helper used by VisualAgent and DemoStepTask.

    Args:
        turn_ctx: The chat context to inject into.
        screenshot: JPEG bytes of the screenshot.
        context_text: Description text shown alongside the screenshot.
        reminder_text: Optional additional reminder text appended after the screenshot.
    """
    # Remove previous screenshot message to prevent token bloat
    turn_ctx.items[:] = [
        item for item in turn_ctx.items
        if not (
            isinstance(item, llm.ChatMessage)
            and item.extra.get(_SCREENSHOT_TAG)
        )
    ]

    content: list = [
        llm.ImageContent(
            image=f"data:image/jpeg;base64,{base64.b64encode(screenshot).decode()}",
            inference_detail="low",
        ),
        context_text,
    ]

    if reminder_text:
        content.append(reminder_text)

    turn_ctx.add_message(
        role="user",
        content=content,
        extra={_SCREENSHOT_TAG: True},
    )


def inject_step_briefing(
    turn_ctx: llm.ChatContext,
    screenshot: bytes,
    guide_text: str,
    step_title: str,
) -> None:
    """Inject a combined briefing (screenshot + page guide + step goal) into context.

    Used by DemoStepTask.on_enter() to give the agent everything it needs in one message.
    Replaces any previous screenshot message.
    """
    # Remove previous screenshot message
    turn_ctx.items[:] = [
        item for item in turn_ctx.items
        if not (
            isinstance(item, llm.ChatMessage)
            and item.extra.get(_SCREENSHOT_TAG)
        )
    ]

    content: list = [
        llm.ImageContent(
            image=f"data:image/jpeg;base64,{base64.b64encode(screenshot).decode()}",
            inference_detail="low",
        ),
        f"[Current browser screen]\n\n{guide_text}",
        f"[Your task: {step_title}. Follow your step instructions — narrate and interact.]",
    ]

    turn_ctx.add_message(
        role="user",
        content=content,
        extra={_SCREENSHOT_TAG: True},
    )


class VisualAgent(Agent):
    """Agent that sees a screen via a screenshot injected on each turn.

    Screenshot source depends on mode:
    - student: instructor's screen share (via InstructorScreenCapture)
    - demo_expert: agent's Playwright browser (via BrowserScreenShare)
    """

    def __init__(
        self,
        *,
        screen_share: BrowserScreenShare,
        instructor_capture: InstructorScreenCapture,
        mode_manager=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._screen_share = screen_share
        self._instructor_capture = instructor_capture
        self._mode_manager = mode_manager

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        # Record activity for silence detector
        if self._mode_manager:
            self._mode_manager.record_activity()

        # Get screenshot from the appropriate source based on mode
        mode = self._mode_manager.state.mode if self._mode_manager else "student"

        if mode == "demo_expert":
            screenshot = await self._screen_share.take_screenshot()
        else:
            screenshot = self._instructor_capture.get_latest_screenshot()

        if screenshot is None:
            return

        if mode == "demo_expert":
            context_text = "[This is your current browser screen. Use it to verify your actions.]"
            reminder_text = "[You're in demo mode. Continue following your demo script.]"
        else:
            context_text = "[This is the instructor's shared screen. Comment on what you see and ask questions about their demo approach.]"
            reminder_text = None

        inject_screenshot_into_context(turn_ctx, screenshot, context_text, reminder_text)
        logger.info(f"Injected {'Playwright' if mode == 'demo_expert' else 'instructor'} screenshot into turn context")
