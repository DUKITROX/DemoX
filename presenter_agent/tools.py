"""Browser interaction tools for the presenter agent (livekit-agents 1.4.x API)."""

import asyncio
import json
import logging
from urllib.parse import urlparse
from livekit.agents import function_tool, RunContext
import redis.asyncio as aioredis

from backend.json_logger import setup_json_logger, log_event

json_logger = setup_json_logger("presenter.tools", "presenter.log")


def _normalize_path(url: str) -> str:
    """Extract and normalize the path from a URL for wiki lookup."""
    path = urlparse(url).path.rstrip("/") or "/"
    return path


def _lookup_page_wiki(page_wikis: dict, current_url: str) -> tuple[str, dict] | None:
    """Look up the best matching page wiki for a URL.

    Tries: exact path match → trailing slash variant → longest prefix match.
    """
    path = _normalize_path(current_url)

    # Exact match
    if path in page_wikis:
        return path, page_wikis[path]

    # Trailing slash variant
    alt = path + "/" if path != "/" else path
    if alt in page_wikis:
        return alt, page_wikis[alt]

    # Prefix match (longest wins)
    best_key = None
    best_len = 0
    for key in page_wikis:
        if path.startswith(key) and len(key) > best_len:
            best_key = key
            best_len = len(key)
    if best_key:
        return best_key, page_wikis[best_key]

    return None


def create_browser_tools(screen_share, room_id: str, redis_url: str = "redis://localhost:6379"):
    """Create the 7 browser interaction tools (shared across both modes)."""

    async def _build_page_guide(current_url: str) -> tuple[str, bool, int]:
        """Build a page guide string for the given URL (research wiki + live scan).

        Returns (guide_text, wiki_found, nav_link_count).
        Shared helper used by get_current_page_guide and auto-load after navigation.
        """
        guide_lines = [f"## Page Guide: {current_url}\n"]
        elements = {}

        # Part 1: Research context (semantic info from researcher)
        wiki = None
        try:
            r = aioredis.from_url(redis_url, decode_responses=True)
            raw = await r.get(f"research:{room_id}")
            await r.aclose()
            if raw:
                data = json.loads(raw)
                page_wikis = data.get("page_wikis", {})
                lookup = _lookup_page_wiki(page_wikis, current_url)
                if lookup:
                    _, wiki = lookup
        except Exception as e:
            guide_lines.append(f"(Could not fetch research: {e})\n")

        if wiki:
            if wiki.get("value_proposition"):
                guide_lines.append(f"**What this page is about:** {wiki['value_proposition']}")
            if wiki.get("talking_points"):
                guide_lines.append("\n### Talking Points")
                for tp in wiki["talking_points"]:
                    guide_lines.append(f"- {tp}")
            if wiki.get("demo_highlights"):
                guide_lines.append("\n### Key Things to Show")
                for h in wiki["demo_highlights"]:
                    guide_lines.append(f"- {h.get('description', '')} (look for: \"{h.get('expected_text', '')}\")")
        else:
            guide_lines.append("(No research context available for this page yet)")

        # Part 2: Live scan of actual clickable elements on the page RIGHT NOW
        try:
            elements = await screen_share.scan_interactive_elements()

            if elements.get("nav_links"):
                guide_lines.append("\n### NAVIGATION LINKS (click these to move between pages)")
                for link in elements["nav_links"]:
                    guide_lines.append(f'- "{link["text"]}" → {link.get("path", "")}')

            if elements.get("buttons"):
                guide_lines.append("\n### BUTTONS on this page")
                for btn in elements["buttons"]:
                    guide_lines.append(f'- "{btn["text"]}"')

            if elements.get("other_links"):
                guide_lines.append("\n### OTHER LINKS on this page")
                for link in elements["other_links"][:15]:
                    guide_lines.append(f'- "{link["text"]}" → {link.get("path", "")}')
                if len(elements["other_links"]) > 15:
                    guide_lines.append(f"  ... and {len(elements['other_links']) - 15} more")

            if elements.get("inputs"):
                guide_lines.append("\n### INPUT FIELDS")
                for inp in elements["inputs"]:
                    guide_lines.append(f'- {inp["text"]}')
        except Exception as e:
            guide_lines.append(f"\n(Live scan failed: {e})")

        guide_lines.append('\n### How to Click')
        guide_lines.append('Use the EXACT text shown in quotes above with click_element.')
        guide_lines.append('Example: click_element("Features") to click the "Features" link.')

        return "\n".join(guide_lines), wiki is not None, len(elements.get("nav_links", []))

    @function_tool(description="Get a detailed guide for the page currently visible in the browser. Call this EVERY TIME you arrive on a new page. Returns: research context (talking points, value prop) AND a live scan of all clickable elements actually on the page right now.")
    async def get_current_page_guide(context: RunContext) -> str:
        current_url = await screen_share.get_current_url()
        if not current_url:
            return "Could not determine current page URL."

        guide_text, wiki_found, nav_count = await _build_page_guide(current_url)

        log_event(json_logger, "tool_call", f"get_current_page_guide: {current_url}", {
            "tool": "get_current_page_guide",
            "room_id": room_id,
            "url": current_url,
            "wiki_found": wiki_found,
            "nav_links": nav_count,
        })
        return guide_text[:15000]

    @function_tool(description="Click a button or link on the page. Pass the element's VISIBLE TEXT (e.g. 'Pricing', 'Start Free Trial', 'Learn More'). The system will find it by role, text, and other matching strategies automatically. If the click causes a page navigation, the new page's guide is automatically included in the response.")
    async def click_element(context: RunContext, selector: str) -> str:
        url_before = await screen_share.get_current_url()
        try:
            await screen_share.click(selector)
            result = f"Clicked element: {selector}"
            success = True
        except Exception as e:
            result = (
                f"Could not find element '{selector}'. "
                "Try using the exact visible text from get_current_page_guide, "
                "or call get_current_page_guide again to see what's clickable. "
                "If nothing works, describe the feature verbally and move on."
            )
            success = False

        # If the click caused a navigation, auto-load the new page's guide
        if success:
            url_after = await screen_share.get_current_url()
            if url_after and url_before and url_after != url_before:
                await asyncio.sleep(1.0)  # Wait for new page to render
                try:
                    guide_text, _, _ = await _build_page_guide(url_after)
                    result += f"\n\nPAGE CHANGED \u2192 auto-loaded guide for new page:\n{guide_text}"
                    log_event(json_logger, "auto_page_guide", f"Auto-loaded guide after nav to {url_after}", {
                        "room_id": room_id,
                        "from_url": url_before,
                        "to_url": url_after,
                    })
                except Exception as e:
                    result += f"\n\n(Page changed to {url_after} but could not load guide: {e})"

        log_event(json_logger, "tool_call", f"click_element: {selector}", {
            "tool": "click_element",
            "room_id": room_id,
            "selector": selector,
            "success": success,
            "result": result[:500],
        })
        return result

    @function_tool(description="Scroll down the page to show more content.")
    async def scroll_down(context: RunContext, pixels: int = 400) -> str:
        await screen_share.scroll_down(pixels)
        log_event(json_logger, "tool_call", f"scroll_down: {pixels}px", {
            "tool": "scroll_down",
            "room_id": room_id,
            "pixels": pixels,
        })
        return f"Scrolled down {pixels}px"

    @function_tool(description="Scroll to bring a specific element into view. Pass the element's visible text (e.g. 'Pricing', 'Contact Us'). The system finds it automatically.")
    async def scroll_to_element(context: RunContext, selector: str) -> str:
        try:
            await screen_share.scroll_to_element(selector)
            result = f"Scrolled to {selector}"
            success = True
        except Exception as e:
            result = (
                f"Could not find element '{selector}'. "
                "Try scroll_down instead to scroll by pixels."
            )
            success = False
        log_event(json_logger, "tool_call", f"scroll_to_element: {selector}", {
            "tool": "scroll_to_element",
            "room_id": room_id,
            "selector": selector,
            "success": success,
            "result": result,
        })
        return result

    @function_tool(description="Highlight an element on the page with an orange outline. Pass the element's visible text (e.g. 'Start Free Trial').")
    async def highlight_element(context: RunContext, selector: str) -> str:
        await screen_share.highlight_element(selector)
        log_event(json_logger, "tool_call", f"highlight_element: {selector}", {
            "tool": "highlight_element",
            "room_id": room_id,
            "selector": selector,
        })
        return f"Highlighted {selector}"

    @function_tool(description="Get the latest research context about the website. Call this when you need more information to answer a user's question.")
    async def get_research_context(context: RunContext) -> str:
        try:
            r = aioredis.from_url(redis_url, decode_responses=True)
            raw = await r.get(f"research:{room_id}")
            await r.aclose()
            if raw:
                data = json.loads(raw)
                log_event(json_logger, "research_context_fetched", "Presenter fetched research context", {
                    "tool": "get_research_context",
                    "room_id": room_id,
                    "data_length": len(raw),
                    "research_status": data.get("status"),
                })
                return json.dumps(data, indent=2)[:15000]
            log_event(json_logger, "research_context_fetched", "Research still in progress", {
                "tool": "get_research_context",
                "room_id": room_id,
                "data_length": 0,
            })
            return "Research is still in progress..."
        except Exception as e:
            return f"Could not fetch research: {e}"

    @function_tool(description="Ask the researcher agent to investigate a specific topic in depth. Use this when the user asks a detailed question you can't answer from current context.")
    async def request_deep_dive(context: RunContext, topic: str, user_question: str = "") -> str:
        try:
            r = aioredis.from_url(redis_url, decode_responses=True)
            await r.publish(
                f"agent_requests:{room_id}",
                json.dumps({
                    "type": "deep_dive_request",
                    "topic": topic,
                    "user_question": user_question,
                }),
            )
            await r.aclose()
            log_event(json_logger, "deep_dive_requested", f"Requested deep dive on '{topic}'", {
                "tool": "request_deep_dive",
                "room_id": room_id,
                "topic": topic,
                "user_question": user_question,
            })
            return f"Requested deep dive on '{topic}'. I'll get more details shortly."
        except Exception as e:
            return f"Could not send request: {e}"

    return [get_current_page_guide, click_element, scroll_down, scroll_to_element,
            highlight_element, get_research_context, request_deep_dive]


def make_save_learning_tool(mode_manager):
    """Create the save_learning tool that closes over the ModeManager."""
    from presenter_agent.mode_state import save_mode_state_to_redis

    @function_tool(
        description="Save something the boss taught you about how to demo. "
        "Call this EVERY TIME the boss shares a tip, workflow step, or insight. "
        "If the boss corrects something, call this again with the same topic to update your notes."
    )
    async def save_learning(context: RunContext, topic: str, details: str) -> str:
        page_url = await mode_manager.screen_share.get_current_url()
        was_update = mode_manager.state.upsert_learning(topic, details, page_url or "")
        await save_mode_state_to_redis(
            mode_manager.state, mode_manager.room_id, mode_manager.redis_url,
        )
        count = len(mode_manager.state.learnings)
        action = "Updated" if was_update else "Noted"
        log_event(json_logger, "save_learning", f"{action}: {topic}", {
            "room_id": mode_manager.room_id,
            "topic": topic,
            "was_update": was_update,
            "total_learnings": count,
        })
        return f"Got it! {action}: '{topic}'. ({count} learning{'s' if count != 1 else ''} total)"

    return save_learning


def make_remove_learning_tool(mode_manager):
    """Create the remove_learning tool that closes over the ModeManager."""
    from presenter_agent.mode_state import save_mode_state_to_redis

    @function_tool(
        description="Remove notes on a topic when the boss says 'forget what I said about X'. "
        "Pass the topic name to remove."
    )
    async def remove_learning(context: RunContext, topic: str) -> str:
        removed = mode_manager.state.remove_learning(topic)
        if removed > 0:
            await save_mode_state_to_redis(
                mode_manager.state, mode_manager.room_id, mode_manager.redis_url,
            )
            remaining = len(mode_manager.state.learnings)
            log_event(json_logger, "remove_learning", f"Removed: {topic}", {
                "room_id": mode_manager.room_id,
                "topic": topic,
                "removed_count": removed,
                "remaining": remaining,
            })
            return f"Removed notes on '{topic}'. ({remaining} learning{'s' if remaining != 1 else ''} remaining)"
        return f"No notes found for '{topic}' — nothing to remove."

    return remove_learning


def make_switch_to_demo_tool(mode_manager):
    """Create the switch_to_demo_mode tool that closes over the ModeManager."""

    @function_tool(
        description="Switch to demo expert mode. Call this when you feel you've learned enough "
        "from the boss to conduct a demo. Usually after 5+ learnings covering different aspects."
    )
    async def switch_to_demo_mode(context: RunContext) -> str:
        num = len(mode_manager.state.learnings)
        if num < 2:
            return (
                f"You only have {num} learning{'s' if num != 1 else ''}. "
                "Keep asking the boss questions to learn more before trying a demo!"
            )
        result = await mode_manager.switch_to_demo()
        log_event(json_logger, "mode_switch", "Switched to demo expert mode", {
            "room_id": mode_manager.room_id,
            "learnings_count": num,
        })
        return result

    return switch_to_demo_mode


def make_switch_to_student_tool(mode_manager):
    """Create the switch_to_student_mode tool that closes over the ModeManager."""

    @function_tool(
        description="Switch back to student/learning mode. Call this when the user wants to "
        "teach you more or asks you to stop the demo and go back to learning."
    )
    async def switch_to_student_mode(context: RunContext) -> str:
        result = await mode_manager.switch_to_student()
        log_event(json_logger, "mode_switch", "Switched back to student mode", {
            "room_id": mode_manager.room_id,
        })
        return result

    return switch_to_student_mode
