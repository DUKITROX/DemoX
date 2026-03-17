"""ModeManager — orchestrates mode switching for the presenter agent."""

import json
import logging

import redis.asyncio as aioredis

from presenter_agent.mode_state import (
    ModeState,
    save_mode_state_to_redis,
)
from presenter_agent.instructions import (
    build_student_instructions,
    build_demo_expert_instructions,
)
from presenter_agent.roadmap_generator import generate_roadmap
from presenter_agent.tools import (
    create_browser_tools,
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

    def __init__(self, screen_share, room_id: str, redis_url: str, url: str):
        self.screen_share = screen_share
        self.room_id = room_id
        self.redis_url = redis_url
        self.url = url
        self.agent = None       # set after Agent() creation
        self.session = None     # set after AgentSession() creation
        self.state = ModeState()
        self._browser_tools = create_browser_tools(screen_share, room_id, redis_url)

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
        """Return tools for Student Mode: browser tools + save/remove learning + switch to demo."""
        return [
            *self._browser_tools,
            make_save_learning_tool(self),
            make_remove_learning_tool(self),
            make_switch_to_demo_tool(self),
        ]

    def get_demo_expert_tools(self) -> list:
        """Return tools for Demo Expert Mode: browser tools + switch to student."""
        return [
            *self._browser_tools,
            make_switch_to_student_tool(self),
        ]

    async def switch_to_demo(self) -> str:
        """Switch from Student to Demo Expert mode.

        Generates a roadmap, updates instructions and tools on the live agent.
        Returns a summary string for the tool response.
        """
        # 1. Generate roadmap from learnings + research
        research = await self._get_research()
        roadmap = await generate_roadmap(
            self.state.learnings, research, self.url,
        )

        # 2. Update state
        self.state.mode = "demo_expert"
        self.state.roadmap = roadmap

        # 3. Build new instructions and tools
        new_instructions = build_demo_expert_instructions(
            self.url, research, self.state.learnings, roadmap,
        )
        new_tools = self.get_demo_expert_tools()

        # 4. Update the live agent
        if self.agent:
            await self.agent.update_instructions(new_instructions)
            await self.agent.update_tools(new_tools)

        # 5. Persist state
        await save_mode_state_to_redis(self.state, self.room_id, self.redis_url)

        # 6. Navigate to home page for demo start
        try:
            await self.screen_share.navigate(self.url)
        except Exception as e:
            logger.warning(f"Could not navigate to home for demo start: {e}")

        steps_count = len(roadmap.steps)
        return (
            f"Mode switched to Demo Expert! Your roadmap has {steps_count} steps. "
            f"Opening: {roadmap.opening_line}"
        )

    async def switch_to_student(self) -> str:
        """Switch from Demo Expert back to Student mode.

        Updates instructions and tools. Sets feedback flag.
        Returns a prompt string for the tool response.
        """
        # 1. Update state
        self.state.mode = "student"
        self.state.demo_feedback_requested = True

        # 2. Build new instructions and tools
        research = await self._get_research()
        new_instructions = build_student_instructions(
            self.url, research, self.state.learnings,
        )
        new_tools = self.get_student_tools()

        # 3. Update the live agent
        if self.agent:
            await self.agent.update_instructions(new_instructions)
            await self.agent.update_tools(new_tools)

        # 4. Persist state
        await save_mode_state_to_redis(self.state, self.room_id, self.redis_url)

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
                self.url, research, self.state.learnings, self.state.roadmap,
            )
