"""Formats visit timeline + learnings + research into a synthesis prompt for roadmap generation.

The LLM receives the instructor's actual browsing session (events grouped by visit)
alongside what they taught, and produces a denoised, actionable demo roadmap.
"""

import json
from dataclasses import dataclass
from presenter_agent.mode_state import Learning, VisitSession, learnings_to_text


@dataclass
class SynthesisResult:
    """Result of format_synthesis_context — text context plus screenshot references."""
    text: str
    screenshots: list[tuple[int, str]]  # list of (visit_index_in_timeline, base64_data)


def _format_visit_events(events: list[dict], max_events: int = 40) -> str:
    """Format a visit's events into a concise readable log.

    Collapses scroll noise and caps total events.
    """
    if not events:
        return "  (no events captured)"

    lines = []
    scroll_count = 0
    scroll_total_px = 0

    for ev in events:
        t = ev.get("type", "")

        # Collapse consecutive scrolls
        if t == "scroll":
            scroll_count += 1
            scroll_total_px += abs(ev.get("delta_y", 0))
            continue

        # Flush accumulated scroll
        if scroll_count > 0:
            direction = "down" if scroll_total_px > 0 else "up"
            lines.append(f"  [scroll] {scroll_count}x {direction}, ~{int(scroll_total_px)}px total")
            scroll_count = 0
            scroll_total_px = 0

        if t == "click":
            text = ev.get("target_text", "")[:60]
            tag = ev.get("tag", "")
            nav = " (in nav)" if ev.get("in_nav") else ""
            lines.append(f'  [click] "{text}" <{tag}>{nav}')
        elif t == "navigation":
            title = ev.get("title", "")
            lines.append(f'  [navigate] → {ev.get("url", "")}  "{title}"')
        elif t == "input":
            label = ev.get("field_label", "")
            ftype = ev.get("field_type", "")
            lines.append(f'  [input] field: "{label}" ({ftype})')
        if len(lines) >= max_events:
            lines.append(f"  ... ({len(events) - max_events} more events)")
            break

    # Flush trailing scroll
    if scroll_count > 0:
        lines.append(f"  [scroll] {scroll_count}x, ~{int(scroll_total_px)}px total")

    return "\n".join(lines)


def _format_learning_with_events(learning: Learning) -> str:
    """Format a single learning with its recent_events context."""
    parts = [f"- **{learning.topic}**: {learning.details}"]
    if learning.page_url:
        parts.append(f"  Page: {learning.page_url}")
    if learning.recent_events:
        parts.append(f"  Context (what instructor was doing when they taught this):")
        parts.append(_format_visit_events(learning.recent_events, max_events=10))
    return "\n".join(parts)


def format_synthesis_context(
    visit_timeline: list[VisitSession],
    learnings: list[Learning],
    research: dict | None,
    url: str,
) -> SynthesisResult:
    """Build the full synthesis context for roadmap generation.

    Combines:
    1. Instructor's visit timeline (events grouped by page visit)
    2. Learnings with their event context
    3. Research data (page wikis, features)

    Returns a SynthesisResult with text and screenshot references.
    """
    sections = []
    screenshots: list[tuple[int, str]] = []
    MAX_SCREENSHOTS = 10

    # Section 1: Visit Timeline
    sections.append("=== INSTRUCTOR'S BROWSING SESSION ===")
    sections.append("The instructor navigated the site in this order. Each visit shows what they clicked,")
    sections.append("scrolled, and typed. Multiple visits to the same page are numbered.\n")

    if visit_timeline:
        for i, visit in enumerate(visit_timeline):
            header = f"Visit #{visit.visit_index} → {visit.page_url}"
            linked = ""
            if visit.learning_topics:
                linked = f" | Learnings taught here: {', '.join(visit.learning_topics)}"
            has_screenshot = visit.screenshot_b64 and len(screenshots) < MAX_SCREENSHOTS
            screenshot_note = " [screenshot included below]" if has_screenshot else ""
            sections.append(f"### {header}{linked}{screenshot_note}")
            sections.append(_format_visit_events(visit.events))
            sections.append("")

            if has_screenshot:
                screenshots.append((i, visit.screenshot_b64))
    else:
        sections.append("(No browsing session captured — generate roadmap from learnings and research only)\n")

    # Section 2: Learnings with event context
    sections.append("=== WHAT THE INSTRUCTOR TAUGHT (with browsing context) ===")
    sections.append("Each learning includes the instructor's recent actions when they shared this insight.\n")

    if learnings:
        for l in learnings:
            sections.append(_format_learning_with_events(l))
            sections.append("")
    else:
        sections.append("(No learnings captured)\n")

    # Section 3: Research data (reuse existing formatter)
    from presenter_agent.roadmap_generator import _format_research
    research_text = _format_research(research)
    sections.append("=== TECHNICAL RESEARCH (page structure, nav links, features) ===")
    sections.append(research_text)

    return SynthesisResult(
        text="\n".join(sections),
        screenshots=screenshots,
    )
