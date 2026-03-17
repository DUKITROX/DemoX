"""Generates a demo roadmap from learnings + research data using Claude Haiku."""

import json
import logging
import os

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from presenter_agent.mode_state import Learning, DemoRoadmap, learnings_to_text

logger = logging.getLogger(__name__)

ROADMAP_PROMPT = """You are a demo strategist. An enthusiastic employee has been learning from their boss \
how to demo a product. Based on what the boss taught them AND technical research about the website, \
create a demo roadmap.

Website URL: {url}

=== WHAT THE BOSS TAUGHT (prioritize this — it reflects how the company actually demos) ===
{learnings_text}

=== TECHNICAL RESEARCH (page structure, nav links, features) ===
{research_text}

Create a demo roadmap as a JSON object:
{{
  "opening_line": "<an engaging opening for the demo, informed by what the boss taught about demo openings>",
  "steps": [
    {{
      "step": 1,
      "page": "<page name, e.g. 'Homepage', 'Pricing'>",
      "action": "<scroll|click|highlight>",
      "target_text": "<EXACT visible text of the element to click/highlight. Must match real text from the research data. null for scroll.>",
      "narration": "<what to say — 2-3 sentences incorporating the boss's tips and talking points>",
      "if_not_found": "<fallback: describe the feature verbally and move on>"
    }}
  ],
  "closing_line": "<natural closing, informed by boss's guidance>"
}}

CRITICAL RULES:
- Prioritize the boss's guidance: if they said "always start with the dashboard", start there.
- The only valid actions are: scroll, click, highlight. There is NO navigate action.
- ALL page transitions MUST be click actions on visible navigation links.
- target_text MUST be EXACT visible text from the research data. Do NOT invent text.
- Do NOT include any CSS selectors. The system finds elements by text automatically.
- Keep to 6-10 steps maximum.
- if_not_found should suggest describing verbally — never suggest URL navigation.
Return ONLY valid JSON."""


def _format_research(research: dict | None) -> str:
    """Format research data for the roadmap generation prompt."""
    if not research or research.get("status") != "complete":
        return "(No research data available — generate roadmap from learnings only)"

    parts = []
    knowledge = research.get("knowledge", {})
    product_name = knowledge.get("product_name", "Unknown")
    parts.append(f"Product: {product_name}")

    features = knowledge.get("all_features", [])
    if features:
        parts.append(f"Features: {', '.join(features[:15])}")

    page_wikis = research.get("page_wikis", {})
    for path, wiki in page_wikis.items():
        parts.append(f"\n--- Page: {path} ({wiki.get('page_title', '')}) ---")
        if wiki.get("value_proposition"):
            parts.append(f"  Value prop: {wiki['value_proposition']}")
        if wiki.get("talking_points"):
            parts.append(f"  Talking points: {'; '.join(wiki['talking_points'][:5])}")
        nav_links = wiki.get("crawled_nav_links", [])
        if nav_links:
            link_texts = [f'"{l["text"]}"' for l in nav_links[:10]]
            parts.append(f"  Nav links: {', '.join(link_texts)}")
        buttons = wiki.get("crawled_buttons", [])
        if buttons:
            btn_texts = [f'"{b["text"]}"' for b in buttons[:10]]
            parts.append(f"  Buttons: {', '.join(btn_texts)}")

    # Include existing demo script outline if available
    demo_script_raw = research.get("demo_script", "")
    if demo_script_raw:
        try:
            script = json.loads(demo_script_raw) if isinstance(demo_script_raw, str) else demo_script_raw
            steps = script.get("demo_steps", [])
            if steps:
                parts.append("\n--- Existing demo script outline (for reference) ---")
                for s in steps[:10]:
                    parts.append(f"  Step {s.get('step', '?')}: [{s.get('action', '')}] {s.get('narration', '')[:100]}")
        except (json.JSONDecodeError, TypeError):
            pass

    return "\n".join(parts)


async def generate_roadmap(
    learnings: list[Learning],
    research: dict | None,
    url: str,
) -> DemoRoadmap:
    """Generate a demo roadmap from learnings + research using Claude Haiku."""
    client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    learnings_text = learnings_to_text(learnings)
    research_text = _format_research(research)

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20241022",
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": ROADMAP_PROMPT.format(
                        url=url,
                        learnings_text=learnings_text,
                        research_text=research_text[:12000],
                    ),
                }
            ],
        )
        text = next(
            block.text for block in response.content if isinstance(block, TextBlock)
        )
        # Strip markdown code fences if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        data = json.loads(text.strip())
        return DemoRoadmap(
            steps=data.get("steps", []),
            opening_line=data.get("opening_line", "Welcome! Let me walk you through our product."),
            closing_line=data.get("closing_line", "That covers the main highlights. Any questions?"),
        )
    except Exception as e:
        logger.error(f"Roadmap generation failed: {e}")
        # Fallback: basic roadmap from learnings
        fallback_steps = [
            {
                "step": 1,
                "page": "Homepage",
                "action": "scroll",
                "target_text": None,
                "narration": "Let me start by scrolling through the homepage to give you an overview.",
                "if_not_found": "Describe what you see on the page",
            }
        ]
        return DemoRoadmap(
            steps=fallback_steps,
            opening_line="Welcome! Let me walk you through what I've learned about this product.",
            closing_line="That covers the highlights. Any questions?",
        )
