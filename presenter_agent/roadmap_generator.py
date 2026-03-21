"""Generates a structured demo roadmap from the notes file + tool reference.

Reads the enriched notes file written during student mode, and produces
a structured roadmap (list of step objects) that the TaskGroup executes
one step at a time. Also writes a human-readable version to disk for debugging.
"""

import json
import logging
import os

from openai import AsyncOpenAI

from backend.config import OPENROUTER_API_KEY, LLM_MODEL, OPENROUTER_BASE_URL
from presenter_agent.mode_state import DemoRoadmap, RoadmapStep, StructuredRoadmap

logger = logging.getLogger(__name__)

TOOL_REFERENCE = """## Available Tools (in-page interaction only — navigation is handled automatically)

- `highlight_element("visible text")` — add an orange outline to an element for 3 seconds
- `scroll_down(pixels)` — scroll the page down (default 400px)
- `scroll_to_element("visible text")` — scroll to bring a specific element into view
- `move_mouse("visible text")` — move the cursor to point at an element without clicking. Use to visually indicate what you're talking about
- `hover_element("visible text")` — hover over an element to show tooltips
- `click_element("visible text")` — click a button/link for in-page interactions (tabs, accordions, expandable sections). NOT for page navigation (that's handled by navigation_action)
- `type_text("field_label", "text")` — type text into a form field found by its label/placeholder

NOTE: get_current_page_guide is NOT available during steps — the page guide is pre-loaded automatically when the agent arrives on each page."""

ROADMAP_PROMPT = """You are a demo strategist creating an executable demo script as structured JSON.

You have the instructor's teaching notes from a training session. Each note maps what the instructor said to what they did in the browser.

Website URL: {url}

=== INSTRUCTOR'S NOTES ===
{notes_content}

=== AVAILABLE TOOLS ===
{tool_reference}

=== YOUR TASK ===
Create a step-by-step demo script as a JSON object. Each step will be executed independently by an AI agent that can only see ONE step at a time. The agent shares its screen and narrates while executing.

=== OUTPUT FORMAT ===
Return a JSON object with this exact structure (no markdown fences, no preamble):

{{
  "opening_line": "A natural opening greeting for the demo, 1-2 sentences",
  "closing_line": "A natural closing that summarizes key takeaways and asks for questions",
  "steps": [
    {{
      "id": "homepage_overview",
      "title": "Homepage Overview",
      "navigation_action": null,
      "instructions": "Welcome the viewer to the homepage. Describe the hero section and the main value proposition you see. Highlight key elements — explain what makes [specific insight from notes] compelling. Point out the main CTA button with move_mouse and explain what it does."
    }},
    {{
      "id": "pricing_page",
      "title": "Pricing Page",
      "navigation_action": "click_element(\\"Pricing\\")",
      "instructions": "Explain that there are [N] tiers designed for different needs — [specific talking points from notes]. Highlight the most popular plan with highlight_element and explain why it's the sweet spot. Point out key feature differences between tiers."
    }}
  ]
}}

=== RULES ===
1. Follow the instructor's teaching ORDER from the notes — this is the demo flow they prefer
2. Use EXACT element text from the notes' "Key actions" lines in tool call arguments
3. ALL page transitions must be via click_element() — put this in navigation_action
4. The first step should have navigation_action: null (agent is already on the homepage)
5. Instructions should focus on WHAT TO SAY and WHAT TO HIGHLIGHT/POINT AT on the page
6. Navigation is handled automatically by the framework — do NOT include click_element for page navigation or get_current_page_guide() in step instructions
7. Instructions should reference specific insights from the notes, not generic filler
8. Instructions should describe what to SAY to the viewer, then what in-page tool to call. Pattern: "Tell the viewer about X, then highlight_element('Y')". NEVER start instructions with a tool call
9. Do NOT invent element text — only use text that appears in the notes
10. If a note mentions hovering/highlighting, include those actions in the step instructions
11. Deduplicate: if multiple notes cover the same page, merge into one step
12. Include move_mouse("text") in instructions to point at elements while narrating
13. End each step's instructions with a natural summary of what was shown. Do NOT include step_complete() — the framework handles step completion automatically
14. Keep steps focused — each step covers ONE page or section, not the entire demo
15. NEVER include meta-directives like "Narrate X" or "Use move_mouse to...". Instead write what the presenter should SAY, followed by the tool call. Example — BAD: "Narrate the pricing tiers." GOOD: "Explain that there are three tiers designed for different team sizes, then highlight_element('Enterprise')."
16. Use click_element in instructions ONLY for in-page interactions (tabs, accordions, expandable sections) — NOT for page-to-page navigation
17. The opening_line is delivered as a separate greeting BEFORE step 1 begins. Step 1 must NOT re-welcome, re-greet, or re-introduce the presenter. Step 1 should jump straight into showing content on the first page
18. Steps must NEVER ask the viewer questions, pause for responses, or "create a personal connection." This is an autonomous, one-way presentation. The agent talks continuously without waiting for input
19. If a step has navigation_action, the agent has ALREADY arrived on the new page when the instructions execute. Write instructions in present tense ("You're now on the pricing page — here you can see...") not transitional ("Let's move to the pricing page")

Return ONLY the JSON object. No code fences, no preamble, no explanation."""


def _domain_filename(url: str, prefix: str = "notes") -> str:
    """Return the file path for a domain's notes or roadmap file."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.hostname or "unknown"
    safe = domain.replace(".", "_").replace("-", "_")
    return os.path.join(prefix, f"{safe}.md")


def _roadmap_to_readable(roadmap: StructuredRoadmap) -> str:
    """Convert a StructuredRoadmap to human-readable markdown for debugging."""
    lines = [f"# Demo Roadmap\n"]
    lines.append(f"**Opening:** {roadmap.opening_line}\n")
    for i, step in enumerate(roadmap.steps, 1):
        lines.append(f"## Step {i}: {step.title}")
        if step.navigation_action:
            lines.append(f"**Navigate:** `{step.navigation_action}`")
        lines.append(f"\n{step.instructions}\n")
    lines.append(f"**Closing:** {roadmap.closing_line}")
    return "\n".join(lines)


def load_roadmap_from_disk(url: str) -> StructuredRoadmap | None:
    """Load a previously generated roadmap JSON from disk.

    Returns None if no roadmap file exists for this URL's domain.
    """
    roadmap_path = _domain_filename(url, "roadmaps")
    json_path = roadmap_path.replace(".md", ".json")

    if not os.path.exists(json_path):
        logger.warning(f"No existing roadmap at {json_path}")
        return None

    try:
        with open(json_path, "r") as f:
            data = json.load(f)

        steps = []
        for step_data in data.get("steps", []):
            steps.append(RoadmapStep(
                id=step_data["id"],
                title=step_data["title"],
                instructions=step_data["instructions"],
                navigation_action=step_data.get("navigation_action"),
            ))

        roadmap = StructuredRoadmap(
            steps=steps,
            opening_line=data.get("opening_line", "Welcome! Let me show you what I've learned."),
            closing_line=data.get("closing_line", "That covers the highlights. Any questions?"),
            file_path=roadmap_path,
        )
        logger.info(f"Loaded existing roadmap with {len(steps)} steps from {json_path}")
        return roadmap

    except Exception as e:
        logger.error(f"Failed to load roadmap from {json_path}: {e}")
        return None


async def generate_roadmap(url: str) -> StructuredRoadmap:
    """Generate a structured demo roadmap from the notes file on disk.

    Returns a StructuredRoadmap with discrete steps for TaskGroup execution.
    Also writes a human-readable version to disk for debugging.
    """
    notes_path = _domain_filename(url, "notes")

    # Read notes file
    notes_content = ""
    if os.path.exists(notes_path):
        with open(notes_path, "r") as f:
            notes_content = f.read()

    if not notes_content.strip():
        notes_content = "(No notes available — generate a basic walkthrough of the homepage)"

    # Build prompt
    prompt = ROADMAP_PROMPT.format(
        url=url,
        notes_content=notes_content[:15000],
        tool_reference=TOOL_REFERENCE,
    )

    roadmap_path = _domain_filename(url, "roadmaps")
    os.makedirs(os.path.dirname(roadmap_path), exist_ok=True)

    try:
        client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            text = "\n".join(lines)

        # Parse JSON
        data = json.loads(text)

        steps = []
        for step_data in data.get("steps", []):
            steps.append(RoadmapStep(
                id=step_data["id"],
                title=step_data["title"],
                instructions=step_data["instructions"],
                navigation_action=step_data.get("navigation_action"),
            ))

        roadmap = StructuredRoadmap(
            steps=steps,
            opening_line=data.get("opening_line", "Welcome! Let me show you what I've learned."),
            closing_line=data.get("closing_line", "That covers the highlights. Any questions?"),
            file_path=roadmap_path,
        )

        # Write human-readable version to disk for debugging
        readable = _roadmap_to_readable(roadmap)
        with open(roadmap_path, "w") as f:
            f.write(readable)

        # Also write raw JSON for inspection
        json_path = roadmap_path.replace(".md", ".json")
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Generated structured roadmap with {len(steps)} steps at {roadmap_path}")

        return roadmap

    except Exception as e:
        logger.error(f"Roadmap generation failed: {e}")
        # Fallback: single-step homepage walkthrough
        fallback_step = RoadmapStep(
            id="homepage_overview",
            title="Homepage Overview",
            instructions=(
                "Narrate what you see — describe the main value proposition and key sections. "
                "Use move_mouse to point at important elements. Scroll down to show more content. "
                "Wrap up by summarizing the key highlights."
            ),
            navigation_action=None,
        )
        roadmap = StructuredRoadmap(
            steps=[fallback_step],
            opening_line="Welcome! Let me walk you through what I've learned about this product.",
            closing_line="That covers the highlights. Any questions?",
            file_path=roadmap_path,
        )

        readable = _roadmap_to_readable(roadmap)
        with open(roadmap_path, "w") as f:
            f.write(readable)

        return roadmap
