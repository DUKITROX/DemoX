import asyncio
import json as _json
import logging
import os
import time as _time
from typing import Callable, Optional, Awaitable

from dotenv import load_dotenv
load_dotenv()

# #region agent log
_DEBUG_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".cursor", "debug.log")
def _debug_log(location, message, data=None, hypothesis_id=None):
    try:
        entry = {"timestamp": int(_time.time() * 1000), "location": location, "message": message}
        if data: entry["data"] = data
        if hypothesis_id: entry["hypothesisId"] = hypothesis_id
        with open(_DEBUG_LOG_PATH, "a") as f:
            f.write(_json.dumps(entry) + "\n")
    except: pass
# #endregion

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.agent.state import SessionState
from backend.agent.prompts import get_system_prompt, get_intent_guard_prompt
from backend.browser.controller import take_screenshot, query_page_content
from backend.browser.actions import execute_computer_action, get_action_coordinate

logger = logging.getLogger(__name__)

COMPUTER_USE_MODEL = "claude-sonnet-4-20250514"
INTENT_GUARD_MODEL = "claude-haiku-4-5-20251001"

# The Computer Use tool definition
COMPUTER_TOOL = {
    "type": "computer_20250124",
    "name": "computer",
    "display_width_px": 1280,
    "display_height_px": 800,
}

PAGE_QUERY_TOOL = {
    "name": "page_query",
    "description": "Execute a JavaScript expression on the current web page to read text, count elements, or inspect page state. Returns the result as a string (max 2000 chars). Use this when you need to read text that is hard to see in screenshots, check exact values, or verify page state.",
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "JavaScript expression to evaluate. Examples: 'document.title', 'document.querySelector(\".result .wpm\").textContent', 'document.querySelectorAll(\".word\").length'",
            }
        },
        "required": ["expression"],
    },
}

MAX_CU_ITERATIONS = 15
MAX_MESSAGE_PAIRS = 5

# Callbacks type alias
TextCallback = Optional[Callable[[str], Awaitable[None]]]
ActionCallback = Optional[Callable[[str], Awaitable[None]]]
ScreenshotCallback = Optional[Callable[[str], Awaitable[None]]]
CursorCallback = Optional[Callable[[int, int], Awaitable[None]]]
BeforeActionsCallback = Optional[Callable[[int], Awaitable[None]]]

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    """Lazy-init the Anthropic client so load_dotenv() has time to run first."""
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.InternalServerError)),
)
async def _call_claude_streaming(
    messages: list,
    system: str,
    on_text_delta: TextCallback = None,
) -> anthropic.types.Message:
    """Call Claude with Computer Use via streaming API for token-by-token text delivery."""
    # Wrap system prompt in a content block with cache_control for prompt caching.
    # This caches the ~2000-token system prompt across all loop iterations,
    # reducing input token costs by ~90% and latency by up to 85% on cache hits.
    system_blocks = [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    request_kwargs = dict(
        model=COMPUTER_USE_MODEL,
        max_tokens=4096,
        system=system_blocks,
        tools=[COMPUTER_TOOL, PAGE_QUERY_TOOL],
        messages=messages,
    )

    beta_flag = os.getenv("ANTHROPIC_COMPUTER_USE_BETA", "computer-use-2025-01-24").strip()

    request_kwargs["betas"] = [beta_flag]

    async with _get_client().beta.messages.stream(**request_kwargs) as stream:
        async for event in stream:
            if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                if on_text_delta:
                    await on_text_delta(event.delta.text)

        response = await stream.get_final_message()

    return response


async def check_intent(user_message: str) -> bool:
    """Quick Haiku check: returns True if the message is off-topic."""
    try:
        response = await _get_client().messages.create(
            model=INTENT_GUARD_MODEL,
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": get_intent_guard_prompt(user_message),
            }],
        )
        text = response.content[0].text.strip().lower()
        return "off_topic" in text
    except Exception as e:
        # If guard fails, let the message through
        return False


def _is_tool_result_message(msg: dict) -> bool:
    """Check if a message is a user message containing only tool_result blocks."""
    if msg.get("role") != "user":
        return False
    content = msg.get("content", [])
    if not isinstance(content, list) or not content:
        return False
    return all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def _trim_messages(messages: list) -> list:
    """Keep roughly the last N user/assistant exchange pairs, trimming at safe
    boundaries so we never start with an orphaned tool_result."""
    if len(messages) <= MAX_MESSAGE_PAIRS * 2:
        return messages

    trimmed = messages[-(MAX_MESSAGE_PAIRS * 2):]

    # Scan forward past any orphaned tool_result/assistant pairs to find a
    # safe start (a regular user message with text/image, not tool_result).
    while trimmed and (_is_tool_result_message(trimmed[0]) or trimmed[0].get("role") == "assistant"):
        trimmed = trimmed[1:]

    if not trimmed:
        trimmed = messages[-2:]

    return trimmed


def _serialize_content(content_blocks) -> list:
    """Convert Anthropic SDK content blocks to serializable dicts for message history."""
    result = []
    for block in content_blocks:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result


async def run_computer_use_loop(
    session: SessionState,
    user_message: str,
    on_text_delta: TextCallback = None,
    on_tool_action: ActionCallback = None,
    on_screenshot: ScreenshotCallback = None,
    on_cursor_move: CursorCallback = None,
    on_before_actions: BeforeActionsCallback = None,
    cancel_event: asyncio.Event = None,
) -> str:
    """
    Main agent loop using Claude Computer Use.

    1. Check intent (off-topic guard)
    2. Take screenshot, build user message
    3. Loop: send to Claude -> execute actions -> take screenshot -> repeat
    4. Return collected text response
    """

    # #region agent log
    msg_summary = [{"i": i, "role": m.get("role"), "types": list({b.get("type") for b in m.get("content", []) if isinstance(b, dict)} if isinstance(m.get("content"), list) else {"text"})} for i, m in enumerate(session.messages)]
    _debug_log("computer_use.py:entry", "messages state on entry", {"count": len(session.messages), "summary": msg_summary}, "H5")
    for i, m in enumerate(session.messages):
        if m.get("role") == "assistant":
            content = m.get("content", [])
            tu_ids = [b.get("id") for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            if tu_ids:
                next_msg = session.messages[i+1] if i+1 < len(session.messages) else None
                next_tr_ids = []
                if next_msg and isinstance(next_msg.get("content"), list):
                    next_tr_ids = [b.get("tool_use_id") for b in next_msg["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
                orphaned = set(tu_ids) - set(next_tr_ids)
                if orphaned:
                    _debug_log("computer_use.py:entry", "PRE-EXISTING ORPHANED tool_use", {"msg_index": i, "orphaned_ids": list(orphaned)}, "H5")
    # #endregion

    # 1. Intent guard
    if await check_intent(user_message):
        rejection = "I appreciate the question, but I'm focused on demonstrating this website right now. Would you like to continue exploring the site?"
        if on_text_delta:
            await on_text_delta(rejection)
        return rejection

    # 2. Take initial screenshot
    screenshot_b64 = await take_screenshot()
    session.last_screenshot_b64 = screenshot_b64
    if on_screenshot:
        await on_screenshot(screenshot_b64)

    # 3. Build user message with screenshot
    user_content = [
        {"type": "text", "text": user_message},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        },
    ]

    # Recover from any pre-existing orphaned tool_use blocks (H5)
    if session.messages and session.messages[-1].get("role") == "assistant":
        last_content = session.messages[-1].get("content", [])
        has_tool_use = any(b.get("type") == "tool_use" for b in last_content if isinstance(b, dict))
        if has_tool_use:
            # #region agent log
            _debug_log("computer_use.py:recovery", "removing orphaned assistant with tool_use before new user msg", {"tool_use_ids": [b.get("id") for b in last_content if isinstance(b, dict) and b.get("type") == "tool_use"]}, "H5")
            # #endregion
            session.messages.pop()

    session.messages.append({"role": "user", "content": user_content})
    session.messages = _trim_messages(session.messages)

    # 4. Agentic loop
    collected_text = []
    system_prompt = get_system_prompt(session)

    for iteration in range(MAX_CU_ITERATIONS):
        # Check for cancellation at the start of each iteration
        if cancel_event and cancel_event.is_set():
            logger.info("Agent loop cancelled by user interruption")
            # Clean up orphaned messages: if last message is an assistant message
            # with tool_use blocks but no corresponding tool_result, remove it
            # to prevent API errors on the next call.
            if session.messages and session.messages[-1].get("role") == "assistant":
                last_content = session.messages[-1].get("content", [])
                has_tool_use = any(
                    b.get("type") == "tool_use" for b in last_content if isinstance(b, dict)
                )
                if has_tool_use:
                    session.messages.pop()
            break

        logger.info(f"CU loop iteration {iteration + 1}")

        # Track how many characters of text are streamed this iteration
        # so the before-actions callback can pace accordingly.
        iteration_text_chars = 0

        async def _counting_text_delta(text: str):
            nonlocal iteration_text_chars
            iteration_text_chars += len(text)
            if on_text_delta:
                await on_text_delta(text)

        try:
            # Stream text deltas in real-time on every iteration so the user
            # sees tokens as they arrive instead of one big dump at the end.
            response = await _call_claude_streaming(
                session.messages, system_prompt, on_text_delta=_counting_text_delta,
            )
        except Exception as e:
            raise

        # Serialize and store assistant response
        assistant_content = _serialize_content(response.content)
        session.messages.append({"role": "assistant", "content": assistant_content})

        # Process response blocks
        tool_use_blocks = []
        for block in response.content:
            if block.type == "text" and block.text.strip():
                collected_text.append(block.text)
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        # #region agent log
        _debug_log("computer_use.py:276", "break check", {"stop_reason": response.stop_reason, "tool_use_count": len(tool_use_blocks), "tool_use_ids": [b.id for b in tool_use_blocks]}, "H1")
        # #endregion

        # If no tool calls, we're done (text was already streamed)
        if not tool_use_blocks:
            break

        # If end_turn but tool_use present, strip the tool_use blocks from
        # the assistant message to prevent orphaned tool_use in history.
        if response.stop_reason == "end_turn":
            # #region agent log
            _debug_log("computer_use.py:276", "end_turn WITH tool_use blocks - stripping tool_use", {"tool_use_ids": [b.id for b in tool_use_blocks]}, "H1")
            # #endregion
            cleaned = [b for b in assistant_content if b.get("type") != "tool_use"]
            if cleaned:
                session.messages[-1]["content"] = cleaned
            else:
                session.messages.pop()
            break

        # Wait for narration to be consumed (TTS or reading time) before acting
        if on_before_actions:
            await on_before_actions(iteration_text_chars)

        # 5. Execute each tool call
        tool_results = []
        try:
            for tool_block in tool_use_blocks:
                # Check for cancellation between tool executions
                if cancel_event and cancel_event.is_set():
                    # #region agent log
                    _debug_log("computer_use.py:cancel", "cancelled during tool exec", {"completed_results": len(tool_results), "total_tools": len(tool_use_blocks)}, "H3")
                    # #endregion
                    logger.info("Agent loop cancelled during tool execution")
                    break

                # Handle page_query tool (DOM inspection, no screenshot needed)
                if tool_block.name == "page_query":
                    expression = tool_block.input.get("expression", "")
                    if on_tool_action:
                        await on_tool_action("page_query")
                    result = await query_page_content(expression)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result,
                    })
                    continue

                # Computer use tool
                action = tool_block.input.get("action", "unknown")

                if on_tool_action:
                    await on_tool_action(action)

                # Execute the browser action (cursor emission handled inside actions.py)
                try:
                    await execute_computer_action(tool_block.input, on_cursor_move=on_cursor_move)
                except Exception as e:
                    logger.error(f"Action '{action}' failed: {e}")

                # Take screenshot after action (action delays are handled in actions.py)
                new_screenshot = await take_screenshot()
                session.last_screenshot_b64 = new_screenshot

                if on_screenshot:
                    await on_screenshot(new_screenshot)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": new_screenshot,
                            },
                        },
                    ],
                })
        except Exception as tool_exec_error:
            # #region agent log
            _debug_log("computer_use.py:tool_exec", "EXCEPTION during tool execution", {"error": str(tool_exec_error), "completed_results": len(tool_results), "total_tools": len(tool_use_blocks)}, "H2")
            # #endregion
            logger.error(f"Tool execution failed: {tool_exec_error}")
            # Fill missing tool_results with error messages to prevent orphaned tool_use
            completed_ids = {r["tool_use_id"] for r in tool_results}
            for tb in tool_use_blocks:
                if tb.id not in completed_ids:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": f"Error: {tool_exec_error}",
                        "is_error": True,
                    })

        # If cancelled mid-execution, fill missing tool_results to avoid orphans
        if cancel_event and cancel_event.is_set():
            completed_ids = {r["tool_use_id"] for r in tool_results}
            for tb in tool_use_blocks:
                if tb.id not in completed_ids:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": "Action cancelled by user",
                        "is_error": True,
                    })

        # Append tool results and continue loop
        session.messages.append({"role": "user", "content": tool_results})

    # #region agent log
    final_summary = [{"i": i, "role": m.get("role"), "types": list({b.get("type") for b in m.get("content", []) if isinstance(b, dict)} if isinstance(m.get("content"), list) else {"text"})} for i, m in enumerate(session.messages)]
    _debug_log("computer_use.py:exit", "messages state on exit", {"count": len(session.messages), "summary": final_summary}, "H2")
    # #endregion

    return "\n".join(collected_text)
