"""Generates a structured demo script from extracted website knowledge."""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

DEMO_SCRIPT_PROMPT = """You are a product demo strategist. Based on the following research about a website, \
create a demo script for a presenter AI agent. The presenter clicks elements by their VISIBLE TEXT — \
it does NOT use CSS selectors. It passes the element's text to a click tool and the system finds it automatically.

Website URL: {url}

Research Data:
{knowledge_json}

Create a demo script as a JSON object with this structure:
{{
  "product_name": "<name of the product/company>",
  "opening_line": "<a natural, engaging opening sentence for the demo>",
  "demo_steps": [
    {{
      "step": 1,
      "page": "<page name where this step happens, e.g. 'Homepage', 'Pricing'>",
      "action": "<scroll|click|highlight>",
      "target_text": "<the element's EXACT visible text to click or highlight, e.g. 'Start Free Trial', 'Pricing'. Must match real text from the research data. null for scroll actions.>",
      "element_description": "<human-readable description: what the element looks like, where it is on the page>",
      "narration": "<what to say while performing this step (2-3 sentences, include specific details)>",
      "if_not_found": "<fallback: 'describe the feature verbally and move on' or 'scroll down to look for it'>"
    }}
  ],
  "key_objection_answers": {{
    "<common question>": "<concise answer>"
  }},
  "closing_line": "<a natural closing/CTA sentence>"
}}

CRITICAL RULES:
- The only valid actions are: scroll, click, highlight. There is NO navigate action.
- ALL page transitions MUST be click actions on visible navigation links. Example: to go to the Pricing page, \
use action "click" with target_text "Pricing" (the nav link text).
- target_text MUST be the element's EXACT visible text as shown in the research data. Do NOT invent text \
that isn't in the data.
- Do NOT include any CSS selectors anywhere. The system finds elements by text automatically.
- Keep the demo to 6-10 steps maximum.
- The if_not_found should suggest describing the feature verbally — never suggest navigating to a URL.
Return ONLY valid JSON.
"""


async def generate_demo_script(
    client: AsyncOpenAI, url: str, knowledge: dict
) -> dict:
    """Generate a structured demo script from website knowledge."""
    try:
        response = await client.chat.completions.create(
            model="google/gemini-3.1-flash-lite-preview",
            max_tokens=5000,
            messages=[
                {
                    "role": "user",
                    "content": DEMO_SCRIPT_PROMPT.format(
                        url=url,
                        knowledge_json=json.dumps(knowledge, indent=2)[:10000],
                    ),
                }
            ],
        )
        text = response.choices[0].message.content
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Demo script generation failed: {e}")
        return {
            "product_name": "Unknown",
            "opening_line": "Welcome! Let me show you around this website.",
            "demo_steps": [
                {
                    "step": 1,
                    "page": "Homepage",
                    "action": "scroll",
                    "target_text": None,
                    "element_description": "Scroll down the homepage to explore content",
                    "narration": "Let me scroll through the homepage to see what this site offers.",
                    "if_not_found": "Describe what you see on the page",
                }
            ],
            "key_objection_answers": {},
            "closing_line": "Thanks for watching the demo!",
        }
