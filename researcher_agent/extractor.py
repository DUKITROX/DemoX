"""Extracts structured knowledge from web page content using Claude.

This extractor receives REAL DOM element data from the crawler and asks Claude
for SEMANTIC analysis only — talking points, value proposition, demo highlights.
It does NOT ask Claude to invent CSS selectors (those come from live DOM scanning).
"""

import json
import logging
import os
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze this webpage and extract structured information for an AI agent \
that will conduct a live demo. The agent already has access to the actual clickable elements \
on the page (provided below). Your job is to provide SEMANTIC understanding — what to talk about, \
what's important, what to highlight.

Page URL: {url}
Page Title: {title}

Page Text Content:
{content}

Actual Interactive Elements Found on This Page:
{dom_elements}

Return ONLY valid JSON with this structure:
{{
  "page_url": "{url}",
  "page_title": "{title}",
  "main_heading": "<primary heading on the page>",
  "value_proposition": "<1-2 sentence summary of what this page/product offers>",
  "key_features": ["<list of 5-10 key features or capabilities mentioned>"],
  "target_audience": "<who this product/page is for>",
  "pricing": {{
    "has_pricing": true/false,
    "tiers": ["<list tier names and prices if visible>"]
  }},
  "page_structure": {{
    "has_hero_section": true/false,
    "has_pricing_section": true/false,
    "has_testimonials": true/false,
    "section_order": ["<list sections top-to-bottom, e.g. hero, features, pricing, testimonials, footer>"]
  }},
  "demo_talking_points": [
    "<5-7 specific talking points a presenter should mention about this page. Include concrete details like numbers, pricing, feature names.>"
  ],
  "demo_highlights": [
    {{
      "description": "<what to highlight and why, e.g. 'The enterprise pricing tier — shows high-value offering'>",
      "expected_text": "<the visible text of the element to highlight, MUST match one of the actual elements listed above>",
      "what_to_say": "<1-2 sentences the presenter should say while highlighting this>"
    }}
  ]
}}

CRITICAL RULES:
- For demo_highlights, the "expected_text" MUST exactly match the text of a real element from the \
"Actual Interactive Elements" list above. Do NOT invent element text that isn't in the list.
- Do NOT include any CSS selectors — the system handles element finding automatically using visible text.
- Focus on providing rich semantic context: what makes this page interesting, what the user should know.
- Be specific in talking points — include actual numbers, feature names, and unique selling points.
"""


async def extract_page_knowledge(
    client: AsyncOpenAI, url: str, title: str, content: str,
    dom_elements: dict | None = None,
) -> dict:
    """Use Gemini to extract semantic knowledge from a single page.

    Args:
        client: OpenAI-compatible API client (OpenRouter)
        url: Page URL
        title: Page title
        content: Page text content
        dom_elements: Real interactive elements from DOM (nav_links, buttons, other_links)
    """
    truncated = content[:20000]

    # Format DOM elements for the prompt
    dom_summary = "None available"
    if dom_elements:
        parts = []
        if dom_elements.get("nav_links"):
            parts.append("Navigation links:")
            for el in dom_elements["nav_links"]:
                parts.append(f'  - "{el["text"]}" → {el.get("path", el.get("href", ""))}')
        if dom_elements.get("buttons"):
            parts.append("Buttons:")
            for el in dom_elements["buttons"]:
                parts.append(f'  - "{el["text"]}"')
        if dom_elements.get("other_links"):
            parts.append("Other links:")
            for el in dom_elements["other_links"][:20]:
                parts.append(f'  - "{el["text"]}" → {el.get("path", el.get("href", ""))}')
        dom_summary = "\n".join(parts) if parts else "No interactive elements found"

    try:
        response = await client.chat.completions.create(
            model="google/gemini-3.1-flash-lite-preview",
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(
                        url=url, title=title, content=truncated,
                        dom_elements=dom_summary,
                    ),
                }
            ],
        )
        text = response.choices[0].message.content
        # Handle markdown code block wrapping
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Extraction failed for {url}: {e}")
        return {
            "page_url": url,
            "page_title": title,
            "error": str(e),
        }
