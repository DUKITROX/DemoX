"""Researcher Agent — crawls and analyzes a website, publishes knowledge via Redis."""

import asyncio
import json
import logging
import os
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
load_dotenv()

from anthropic import AsyncAnthropic
from playwright.async_api import async_playwright
import redis.asyncio as aioredis

from researcher_agent.extractor import extract_page_knowledge
from researcher_agent.summarizer import generate_demo_script

from backend.json_logger import setup_json_logger, log_event

logger = setup_json_logger("researcher", "researcher.log")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MAX_PAGES = 4


def normalize_url_path(url: str) -> str:
    """Extract and normalize URL path for use as a page wiki key."""
    path = urlparse(url).path.rstrip("/") or "/"
    return path


def build_page_wikis(all_knowledge: list[dict], pages_data: list[dict]) -> dict:
    """Build a dict of per-page wikis keyed by normalized URL path.

    Combines semantic analysis from Claude (talking points, value prop) with
    real DOM element data from the crawl (actual links, buttons).
    """
    # Index pages_data by URL for lookup
    dom_by_url = {}
    for pd in pages_data:
        dom_by_url[pd["url"]] = pd.get("dom_elements", {})

    wikis = {}
    for page_k in all_knowledge:
        page_url = page_k.get("page_url", "")
        if not page_url:
            continue
        path = normalize_url_path(page_url)
        dom = dom_by_url.get(page_url, {})
        wikis[path] = {
            "page_url": page_url,
            "page_title": page_k.get("page_title", ""),
            "value_proposition": page_k.get("value_proposition", ""),
            "talking_points": page_k.get("demo_talking_points", []),
            "demo_highlights": page_k.get("demo_highlights", []),
            "page_structure": page_k.get("page_structure", {}),
            "pricing": page_k.get("pricing", {}),
            # Real DOM elements from crawl (presenter also does live scan, but this is useful context)
            "crawled_nav_links": dom.get("nav_links", []),
            "crawled_buttons": dom.get("buttons", []),
        }
    return wikis


EXTRACT_DOM_ELEMENTS_JS = """
() => {
    function isVisible(el) {
        if (!el.offsetParent && el.tagName !== 'BODY') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    function isInNav(el) {
        let node = el;
        while (node) {
            if (node.tagName === 'NAV') return true;
            if (node.getAttribute && node.getAttribute('role') === 'navigation') return true;
            node = node.parentElement;
        }
        return false;
    }

    const result = {nav_links: [], buttons: [], other_links: []};

    // Collect all visible links
    for (const a of document.querySelectorAll('a[href]')) {
        if (!isVisible(a)) continue;
        const text = (a.innerText || a.getAttribute('aria-label') || '').trim();
        if (!text || text.length > 100) continue;
        const entry = {
            text: text,
            href: a.href,
            path: new URL(a.href, location.origin).pathname,
            in_nav: isInNav(a),
        };
        if (entry.in_nav) {
            result.nav_links.push(entry);
        } else {
            result.other_links.push(entry);
        }
    }

    // Collect all visible buttons
    const btnSel = 'button, [role="button"], input[type="submit"], input[type="button"]';
    for (const btn of document.querySelectorAll(btnSel)) {
        if (!isVisible(btn)) continue;
        const text = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim();
        if (!text || text.length > 100) continue;
        result.buttons.push({text: text});
    }

    return result;
}
"""


async def crawl_pages(browser, start_url: str) -> list[dict]:
    """Crawl the website starting from the given URL, collecting page data and real DOM elements."""
    visited = set()
    pages_data = []
    to_visit = [start_url]
    base_domain = urlparse(start_url).netloc

    page = await browser.new_page(viewport={"width": 1280, "height": 720})

    while to_visit and len(pages_data) < MAX_PAGES:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)  # Let JS render

            title = await page.title()
            content = await page.evaluate("document.body.innerText")

            # Extract real interactive elements from the DOM
            dom_elements = await page.evaluate(EXTRACT_DOM_ELEMENTS_JS)

            # Collect internal links for crawl queue
            all_links = dom_elements.get("nav_links", []) + dom_elements.get("other_links", [])
            link_hrefs = [l["href"] for l in all_links if l.get("href", "").startswith("http")]

            pages_data.append({
                "url": url,
                "title": title,
                "content": content[:20000],
                "dom_elements": dom_elements,
            })
            log_event(logger, "page_crawled", f"Crawled: {title} ({url})", {
                "url": url,
                "title": title,
                "content_length": len(content),
                "links_found": len(link_hrefs),
                "nav_links": len(dom_elements.get("nav_links", [])),
                "buttons": len(dom_elements.get("buttons", [])),
                "pages_crawled_so_far": len(pages_data),
            })

            # Add internal links to visit queue
            for href in link_hrefs:
                parsed = urlparse(href)
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.netloc == base_domain and clean_url not in visited:
                    to_visit.append(clean_url)

        except Exception as e:
            log_event(logger, "crawl_failed", f"Failed to crawl {url}: {e}", {
                "url": url,
                "error": str(e),
            }, level=logging.WARNING)

    await page.close()
    return pages_data


async def research_website(room_id: str, website_url: str):
    """Main research pipeline — crawl, extract, summarize, publish."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # Publish initial status
    await r.set(
        f"research:{room_id}",
        json.dumps({"status": "researching", "knowledge": {}, "demo_script": ""}),
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # Step 1: Crawl pages
        log_event(logger, "crawl_start", f"Starting crawl of {website_url}", {
            "room_id": room_id,
            "website_url": website_url,
            "max_pages": MAX_PAGES,
        })
        pages_data = await crawl_pages(browser, website_url)
        log_event(logger, "crawl_complete", f"Crawled {len(pages_data)} pages", {
            "room_id": room_id,
            "pages_crawled": len(pages_data),
        })

        # Step 2: Extract knowledge from each page (pass real DOM elements)
        all_knowledge = []
        for page_data in pages_data:
            knowledge = await extract_page_knowledge(
                client,
                page_data["url"],
                page_data["title"],
                page_data["content"],
                page_data.get("dom_elements", {}),
            )
            all_knowledge.append(knowledge)
            log_event(logger, "knowledge_extracted", f"Extracted knowledge from {page_data['url']}", {
                "room_id": room_id,
                "page_url": page_data["url"],
                "features_count": len(knowledge.get("key_features", [])),
                "highlights_count": len(knowledge.get("demo_highlights", [])),
                "talking_points_count": len(knowledge.get("demo_talking_points", [])),
            })

            # Publish incremental updates (include page_wikis so presenter can use them immediately)
            incremental_wikis = build_page_wikis(all_knowledge, pages_data)
            await r.set(
                f"research:{room_id}",
                json.dumps({
                    "status": "extracting",
                    "knowledge": {
                        "pages_analyzed": len(all_knowledge),
                        "total_pages": len(pages_data),
                        "pages": all_knowledge,
                    },
                    "demo_script": "",
                    "page_wikis": incremental_wikis,
                }),
            )

        # Step 3: Combine knowledge and generate demo script
        combined_knowledge = {
            "product_name": all_knowledge[0].get("main_heading", "Unknown") if all_knowledge else "Unknown",
            "website_url": website_url,
            "pages": all_knowledge,
            "all_features": [],
        }

        # Aggregate and deduplicate features across pages
        for k in all_knowledge:
            combined_knowledge["all_features"].extend(k.get("key_features", []))
        combined_knowledge["all_features"] = list(set(combined_knowledge["all_features"]))

        log_event(logger, "demo_script_generating", "Generating demo script...", {
            "room_id": room_id,
        })
        demo_script = await generate_demo_script(client, website_url, combined_knowledge)

        # Update product name from demo script if available
        if demo_script.get("product_name") and demo_script["product_name"] != "Unknown":
            combined_knowledge["product_name"] = demo_script["product_name"]

        # Build per-page wikis for the presenter
        page_wikis = build_page_wikis(all_knowledge, pages_data)
        log_event(logger, "page_wikis_built", f"Built {len(page_wikis)} page wikis", {
            "room_id": room_id,
            "wiki_paths": list(page_wikis.keys()),
        })

        # Step 4: Publish final results
        final_data = {
            "status": "complete",
            "knowledge": combined_knowledge,
            "demo_script": json.dumps(demo_script, indent=2),
            "page_wikis": page_wikis,
        }
        await r.set(f"research:{room_id}", json.dumps(final_data))
        await r.publish(f"research_updates:{room_id}", json.dumps(final_data))
        log_event(logger, "research_complete", f"Research complete for room {room_id}", {
            "room_id": room_id,
            "pages_analyzed": len(all_knowledge),
            "total_features": len(combined_knowledge.get("all_features", [])),
            "demo_steps": len(demo_script.get("demo_steps", [])),
            "product_name": demo_script.get("product_name", "Unknown"),
        })

        # Step 5: Monitor for deep dive requests
        await monitor_requests(browser, client, r, room_id, website_url)

        await browser.close()


async def monitor_requests(browser, client, r, room_id: str, base_url: str):
    """Listen for deep dive requests from the presenter agent."""
    pubsub = r.pubsub()
    await pubsub.subscribe(f"agent_requests:{room_id}")

    log_event(logger, "monitoring_start", f"Monitoring for deep dive requests on room {room_id}", {
        "room_id": room_id,
    })

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        try:
            request = json.loads(message["data"])
            if request.get("type") == "deep_dive_request":
                topic = request.get("topic", "")
                user_question = request.get("user_question", "")
                log_event(logger, "deep_dive_request", f"Deep dive request: {topic} - {user_question}", {
                    "room_id": room_id,
                    "topic": topic,
                    "user_question": user_question,
                })

                # Research the specific topic
                page = await browser.new_page(viewport={"width": 1280, "height": 720})
                try:
                    # Try navigating to a relevant sub-page
                    search_url = f"{base_url.rstrip('/')}/{topic.lower().replace(' ', '-')}"
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=10000)
                    await asyncio.sleep(1)
                    content = await page.evaluate("document.body.innerText")
                    title = await page.title()
                    dom_elements = await page.evaluate(EXTRACT_DOM_ELEMENTS_JS)

                    deep_knowledge = await extract_page_knowledge(
                        client, search_url, title, content, dom_elements
                    )

                    # Update research with deep dive results
                    raw = await r.get(f"research:{room_id}")
                    if raw:
                        data = json.loads(raw)
                        data.setdefault("deep_dives", []).append({
                            "topic": topic,
                            "question": user_question,
                            "result": deep_knowledge,
                        })
                        await r.set(f"research:{room_id}", json.dumps(data))
                        await r.publish(f"research_updates:{room_id}", json.dumps(data))
                    log_event(logger, "deep_dive_complete", f"Deep dive complete for {topic}", {
                        "room_id": room_id,
                        "topic": topic,
                        "user_question": user_question,
                        "knowledge_keys": list(deep_knowledge.keys()),
                    })
                except Exception as e:
                    log_event(logger, "deep_dive_failed", f"Deep dive failed for {topic}: {e}", {
                        "room_id": room_id,
                        "topic": topic,
                        "error": str(e),
                    }, level=logging.WARNING)
                finally:
                    await page.close()

        except Exception as e:
            logger.error(f"Error processing request: {e}")


async def main():
    room_id = os.environ.get("ROOM_ID")
    website_url = os.environ.get("WEBSITE_URL")

    if not room_id or not website_url:
        logger.error("ROOM_ID and WEBSITE_URL environment variables required")
        return

    log_event(logger, "researcher_start", f"Starting researcher for room={room_id}, url={website_url}", {
        "room_id": room_id,
        "website_url": website_url,
    })
    await research_website(room_id, website_url)


if __name__ == "__main__":
    asyncio.run(main())
