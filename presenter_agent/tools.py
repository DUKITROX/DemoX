"""Browser interaction tools for the presenter agent (livekit-agents 1.4.x API)."""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from livekit.agents import function_tool, RunContext
import redis.asyncio as aioredis
from openai import AsyncOpenAI

from backend.config import OPENROUTER_API_KEY, LLM_MODEL, OPENROUTER_BASE_URL
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


async def build_page_guide(screen_share, room_id: str, redis_url: str, current_url: str) -> tuple[str, bool, int]:
    """Build a page guide string for the given URL (research wiki + live scan).

    Returns (guide_text, wiki_found, nav_link_count).
    Top-level function used by get_current_page_guide tool and DemoStepTask.on_enter().
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


def create_browser_tools(screen_share, room_id: str, redis_url: str = "redis://localhost:6379",
                          on_tool_activity=None):
    """Create the browser interaction tools (shared across both modes)."""

    @function_tool(description="Get a detailed guide for the page currently visible in the browser. Call this EVERY TIME you arrive on a new page. Returns: research context (talking points, value prop) AND a live scan of all clickable elements actually on the page right now.")
    async def get_current_page_guide(context: RunContext) -> str:
        if on_tool_activity:
            on_tool_activity()
        current_url = await screen_share.get_current_url()
        if not current_url:
            return "Could not determine current page URL."

        guide_text, wiki_found, nav_count = await build_page_guide(
            screen_share, room_id, redis_url, current_url,
        )

        log_event(json_logger, "tool_call", f"get_current_page_guide: {current_url}", {
            "tool": "get_current_page_guide",
            "room_id": room_id,
            "url": current_url,
            "wiki_found": wiki_found,
            "nav_links": nav_count,
        })
        return guide_text[:15000]

    @function_tool(description="Click a button or link on the page. Pass the element's VISIBLE TEXT (e.g. 'Pricing', 'Start Free Trial', 'Learn More'). The system will find it by role, text, and other matching strategies automatically. Returns whether the page URL changed after clicking.")
    async def click_element(context: RunContext, selector: str) -> str:
        if on_tool_activity:
            on_tool_activity()
        try:
            url_before = await screen_share.get_current_url()
            await screen_share.click(selector)
            await asyncio.sleep(0.5)  # let SPA routing / animations settle
            url_after = await screen_share.get_current_url()

            if url_after and url_before and url_after != url_before:
                result = (
                    f"Clicked '{selector}' — navigated to {url_after}. "
                    "Call get_current_page_guide() now to see what's on this new page."
                )
            else:
                result = (
                    f"Clicked '{selector}' (stayed on same page: {url_after or 'unknown'}). "
                    "Verify the click had the expected effect — if it should have navigated, "
                    "try get_current_page_guide() to check, or try a different element."
                )
            success = True
        except Exception as e:
            result = (
                f"Could not find element '{selector}'. "
                "Try using the exact visible text from get_current_page_guide, "
                "or call get_current_page_guide again to see what's clickable. "
                "If nothing works, describe the feature verbally and move on."
            )
            success = False

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
        if on_tool_activity:
            on_tool_activity()
        await screen_share.scroll_down(pixels)
        log_event(json_logger, "tool_call", f"scroll_down: {pixels}px", {
            "tool": "scroll_down",
            "room_id": room_id,
            "pixels": pixels,
        })
        return f"Scrolled down {pixels}px"

    @function_tool(description="Scroll to bring a specific element into view. Pass the element's visible text (e.g. 'Pricing', 'Contact Us'). The system finds it automatically.")
    async def scroll_to_element(context: RunContext, selector: str) -> str:
        if on_tool_activity:
            on_tool_activity()
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
        if on_tool_activity:
            on_tool_activity()
        await screen_share.highlight_element(selector)
        log_event(json_logger, "tool_call", f"highlight_element: {selector}", {
            "tool": "highlight_element",
            "room_id": room_id,
            "selector": selector,
        })
        return f"Highlighted {selector}"

    @function_tool(description="Get the latest research context about the website. Call this when you need more information to answer a user's question.")
    async def get_research_context(context: RunContext) -> str:
        if on_tool_activity:
            on_tool_activity()
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
        if on_tool_activity:
            on_tool_activity()
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

    @function_tool(description="Type text into a form field. Pass the field's label, placeholder, or aria-label to find it, and the text to type. Use contextually appropriate values (not real user data).")
    async def type_text(context: RunContext, field_label: str, text: str) -> str:
        if on_tool_activity:
            on_tool_activity()
        try:
            await screen_share.type_in_field(field_label, text)
            result = f"Typed '{text}' into field '{field_label}'"
            success = True
        except Exception as e:
            result = (
                f"Could not find field '{field_label}'. "
                "Try using the exact label from get_current_page_guide."
            )
            success = False
        log_event(json_logger, "tool_call", f"type_text: {field_label}", {
            "tool": "type_text",
            "room_id": room_id,
            "field_label": field_label,
            "success": success,
        })
        return result

    @function_tool(description="Hover the cursor over an element by its visible text. Use this to show tooltips or draw attention to an element without clicking it.")
    async def hover_element(context: RunContext, text: str) -> str:
        if on_tool_activity:
            on_tool_activity()
        try:
            await screen_share.hover(text)
            result = f"Hovering over '{text}'"
            success = True
        except Exception as e:
            result = f"Could not find element '{text}' to hover."
            success = False
        log_event(json_logger, "tool_call", f"hover_element: {text}", {
            "tool": "hover_element",
            "room_id": room_id,
            "text": text,
            "success": success,
        })
        return result

    @function_tool(description="Move the cursor to point at an element without clicking or hovering. Use this to visually indicate what you're talking about. Pass the element's visible text.")
    async def move_mouse(context: RunContext, text: str) -> str:
        if on_tool_activity:
            on_tool_activity()
        try:
            await screen_share.move_mouse_to(text)
            result = f"Moved cursor to '{text}'"
            success = True
        except Exception as e:
            result = f"Could not find element '{text}' to point at."
            success = False
        log_event(json_logger, "tool_call", f"move_mouse: {text}", {
            "tool": "move_mouse",
            "room_id": room_id,
            "text": text,
            "success": success,
        })
        return result

    tools = [get_current_page_guide, click_element, scroll_down, scroll_to_element,
             highlight_element, type_text, hover_element, move_mouse, get_research_context, request_deep_dive]
    return tools


def _domain_filename(url: str, prefix: str = "notes") -> str:
    """Return the file path for a domain's notes or roadmap file.

    E.g. _domain_filename("https://app.example.com/pricing", "notes") -> "notes/app_example_com.md"
    """
    parsed = urlparse(url)
    domain = parsed.hostname or "unknown"
    safe = domain.replace(".", "_").replace("-", "_")
    return os.path.join(prefix, f"{safe}.md")


def _filter_events(events: list[dict]) -> list[dict]:
    """Filter events to meaningful ones only. Drop scroll noise."""
    meaningful = []
    for ev in events:
        t = ev.get("type", "")
        if t == "click":
            meaningful.append({
                "type": "click",
                "target_text": ev.get("target_text", "")[:80],
                "tag": ev.get("tag", ""),
                "page_url": ev.get("url", ""),
                "in_nav": ev.get("in_nav", False),
            })
        elif t == "navigation":
            meaningful.append({
                "type": "navigation",
                "url": ev.get("url", ""),
                "title": ev.get("title", ""),
            })
        elif t == "input":
            meaningful.append({
                "type": "input",
                "field_label": ev.get("field_label", ""),
                "text": ev.get("text", "")[:80],
            })
        elif t in ("mouseenter", "hover"):
            if ev.get("target_text"):
                meaningful.append({
                    "type": "hover",
                    "target_text": ev.get("target_text", "")[:80],
                })
        # Drop scroll events entirely
    return meaningful


async def _enrich_learning(topic: str, details: str, events: list[dict], page_url: str) -> str:
    """Call LLM to synthesize a rich demo note from teaching + filtered events."""
    events_text = ""
    if events:
        event_lines = []
        for ev in events:
            if ev["type"] == "click":
                nav = " (in nav)" if ev.get("in_nav") else ""
                event_lines.append(f'- Clicked "{ev["target_text"]}" <{ev["tag"]}>{nav}')
            elif ev["type"] == "navigation":
                event_lines.append(f'- Navigated to {ev["url"]} ("{ev.get("title", "")}")')
            elif ev["type"] == "input":
                event_lines.append(f'- Typed into field "{ev["field_label"]}": "{ev["text"]}"')
            elif ev["type"] == "hover":
                event_lines.append(f'- Hovered over "{ev["target_text"]}"')
        events_text = "\n".join(event_lines)

    prompt = f"""Write a concise demo note that maps what the instructor taught to what they did in the browser.

Topic: {topic}
What the instructor said: {details}
Current page: {page_url}

Browser actions during this teaching:
{events_text if events_text else "(no browser actions captured)"}

Write a 3-6 sentence paragraph that:
1. Describes what the instructor did in the browser (navigated to X, clicked Y, hovered Z)
2. Maps those actions to what they taught (they clicked X "because..." / "to show...")
3. Ends with a "Key actions:" line listing tool calls needed to reproduce this (e.g. click "Pricing", hover "Calculate Savings", type_text("Search", "Q1 Revenue"))

Use the EXACT text from click/hover targets — these will be used as tool arguments later.
Do NOT use markdown headers or formatting. Just a plain paragraph followed by the Key actions line."""

    try:
        client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log_event(json_logger, "enrich_learning_failed", str(e), {})
        # Fallback: manual formatting
        parts = [f"{details}"]
        if events_text:
            parts.append(f"\nKey actions: {events_text}")
        return "\n".join(parts)


def _append_to_notes_file(url: str, topic: str, page_url: str, enriched_note: str):
    """Append an enriched note to the domain's notes file."""
    filepath = _domain_filename(url, "notes")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Create file with header if it doesn't exist
    if not os.path.exists(filepath):
        parsed = urlparse(url)
        domain = parsed.hostname or "unknown"
        with open(filepath, "w") as f:
            f.write(f"# Demo Notes: {domain}\n")
            f.write(f"URL: {url}\n\n")

    # Parse page path for display
    page_path = urlparse(page_url).path if page_url else "/"

    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

    with open(filepath, "a") as f:
        f.write(f"## {topic}\n")
        f.write(f"**Page:** {page_path}\n")
        f.write(f"**Time:** {timestamp}\n\n")
        f.write(f"{enriched_note}\n\n")
        f.write("---\n\n")


def create_student_tools(room_id: str, redis_url: str = "redis://localhost:6379"):
    """Create tools available in Student Mode (no browser — only research access)."""

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

    return [get_research_context, request_deep_dive]


def make_save_learning_tool(mode_manager):
    """Create the save_learning tool that closes over the ModeManager."""
    from presenter_agent.mode_state import save_mode_state_to_redis
    from backend.events import get_events

    @function_tool(
        description="Save something the boss taught you about how to demo. "
        "Call this EVERY TIME the boss shares a tip, workflow step, or insight. "
        "If the boss corrects something, call this again with the same topic to update your notes."
    )
    async def save_learning(context: RunContext, topic: str, details: str) -> str:
        # Get page URL from visit timeline (no Playwright in student mode)
        if mode_manager.state.visit_timeline:
            page_url = mode_manager.state.visit_timeline[-1].page_url
        else:
            page_url = mode_manager.url
        now = time.time()

        # Fetch events since last watermark (not last 15s — avoids overlap)
        raw_events = []
        try:
            raw_events = await get_events(
                mode_manager.room_id,
                since=mode_manager.state.event_watermark,
                limit=200,
            )
        except Exception as e:
            log_event(json_logger, "events_fetch_failed", str(e), {
                "room_id": mode_manager.room_id,
            })

        # Filter to meaningful events
        filtered = _filter_events(raw_events)

        # Enrich via LLM
        enriched_note = await _enrich_learning(topic, details, filtered, page_url or "")

        # Append to notes file on disk
        _append_to_notes_file(mode_manager.url, topic, page_url or "", enriched_note)

        # Update watermark and nudge timer
        mode_manager.state.event_watermark = now
        mode_manager.record_save_learning()

        # Also update in-memory learnings (agent needs them in student context)
        was_update = mode_manager.state.upsert_learning(
            topic, details, page_url or "", recent_events=filtered,
        )

        # Link learning to current visit session
        mode_manager.state.link_learning_to_current_visit(topic)

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
            "filtered_events": len(filtered),
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
    """Create the switch_to_demo_mode tool that closes over the ModeManager.

    This tool:
    1. Starts Playwright and generates a structured roadmap (via mode_manager.prepare_demo)
    2. Creates a TaskGroup from the roadmap steps
    3. Awaits the TaskGroup — each step executes one at a time
    4. After completion or abort, switches back to student mode
    """
    from presenter_agent.demo_task import create_demo_task_group

    @function_tool(
        description="Switch to demo expert mode and start a live screen-shared demo. "
        "Call this IMMEDIATELY when the boss tells you to do the demo or start the demo. "
        "Also call this proactively when you have 5+ learnings covering different aspects."
    )
    async def switch_to_demo_mode(context: RunContext) -> str:
        num = len(mode_manager.state.learnings)
        if num < 2:
            return (
                f"You only have {num} learning{'s' if num != 1 else ''}. "
                "Keep asking the boss questions to learn more before trying a demo!"
            )

        # 1. Prepare: start Playwright, generate roadmap, navigate home, start publishing
        roadmap = await mode_manager.prepare_demo()
        if roadmap is None:
            return "Could not prepare the demo — browser or roadmap generation failed."

        log_event(json_logger, "mode_switch", "Starting demo with TaskGroup", {
            "room_id": mode_manager.room_id,
            "learnings_count": num,
            "roadmap_steps": len(roadmap.steps),
        })

        # 2. Create reduced tool set for TaskGroup steps (no page guide/research)
        browser_tools = mode_manager.get_demo_step_tools()

        # 3. Create and run TaskGroup
        # Get chat_ctx from the current agent
        chat_ctx = mode_manager.agent.chat_ctx if mode_manager.agent else None

        task_group = create_demo_task_group(
            roadmap=roadmap,
            browser_tools=browser_tools,
            screen_share=mode_manager.screen_share,
            url=mode_manager.url,
            chat_ctx=chat_ctx,
            room_id=mode_manager.room_id,
            redis_url=mode_manager.redis_url,
        )

        # Store reference so manual mode switch can cancel it
        mode_manager.active_task_group = task_group

        try:
            # 4. Await the TaskGroup — blocks until all steps complete or aborted
            results = await task_group

            # 5. Check if any step was aborted
            aborted = False
            if results and hasattr(results, 'task_results'):
                for task_id, result in results.task_results.items():
                    if result is False:
                        aborted = True
                        break

            log_event(json_logger, "demo_complete",
                      f"Demo {'aborted' if aborted else 'completed'}", {
                          "room_id": mode_manager.room_id,
                          "aborted": aborted,
                      })

        except Exception as e:
            log_event(json_logger, "demo_error", f"TaskGroup error: {e}", {
                "room_id": mode_manager.room_id,
                "error": str(e),
            })
        finally:
            mode_manager.active_task_group = None

        # 6. Switch back to student mode after demo ends
        result = await mode_manager.switch_to_student()
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
