"""Screen share module — captures Playwright browser and publishes as LiveKit video track."""

import asyncio
import io
import logging
import re

import numpy as np
from PIL import Image
from playwright.async_api import async_playwright, Page, Browser, Locator
from livekit import rtc

logger = logging.getLogger(__name__)


def sanitize_selector(selector: str) -> str:
    """Convert common invalid LLM-generated selectors to valid Playwright selectors.

    Handles patterns like:
    - :contains('X') → :has-text("X")
    - text=X (bare) → already valid in Playwright
    - Strips leading/trailing whitespace
    """
    s = selector.strip()

    # Convert jQuery :contains('...') or :contains("...") to Playwright :has-text("...")
    s = re.sub(
        r""":contains\(\s*['"](.+?)['"]\s*\)""",
        lambda m: f':has-text("{m.group(1)}")',
        s,
    )

    return s


def _extract_text_from_selector(selector: str) -> str | None:
    """Try to extract a human-readable text target from a selector pattern.

    Looks for patterns like:
    - :has-text("Pricing")
    - :contains('Pricing')
    - text=Pricing / text="Pricing"
    - [aria-label='Pricing']
    - >> text content after last combinator
    """
    # :has-text("...") or :contains("...")
    m = re.search(r"""(?::has-text|:contains)\(\s*['"](.+?)['"]\s*\)""", selector)
    if m:
        return m.group(1)

    # text=... or text="..."
    m = re.search(r"""text\s*=\s*['"]?(.+?)['"]?\s*$""", selector)
    if m:
        return m.group(1)

    return None


def _extract_aria_label(selector: str) -> str | None:
    """Extract aria-label value from selector like [aria-label='X']."""
    m = re.search(r"""\[aria-label\s*=\s*['"](.+?)['"]\]""", selector)
    if m:
        return m.group(1)
    return None

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
TARGET_FPS = 30

# JavaScript to inject a custom cursor overlay and smooth movement animation.
# Takes [initX, initY] as argument so cursor resumes at stored position after navigation.
CURSOR_INJECT_JS = """
([initX, initY]) => {
    if (document.getElementById('__demo_cursor')) return;

    const cursor = document.createElement('div');
    cursor.id = '__demo_cursor';
    cursor.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M5 3L19 12L12 13L9 20L5 3Z" fill="white" stroke="black" stroke-width="2" stroke-linejoin="round"/>
        </svg>
    `;
    cursor.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 36px;
        height: 36px;
        z-index: 2147483647;
        pointer-events: none;
        transition: none;
        transform: translate(${initX}px, ${initY}px);
        filter: drop-shadow(2px 3px 3px rgba(0,0,0,0.5));
    `;
    document.body.appendChild(cursor);

    // Store current position (passed from Python-side state)
    window.__cursorX = initX;
    window.__cursorY = initY;

    // Smooth scroll function using requestAnimationFrame
    window.__smoothScrollBy = (deltaY, durationMs) => {
        const startY = window.scrollY;
        const startTime = performance.now();
        function ease(t) {
            return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        }
        function step(now) {
            const progress = Math.min((now - startTime) / durationMs, 1);
            window.scrollTo(0, startY + deltaY * ease(progress));
            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    };

    // Smooth move function using requestAnimationFrame
    window.__moveCursorTo = (targetX, targetY, durationMs) => {
        return new Promise(resolve => {
            const startX = window.__cursorX;
            const startY = window.__cursorY;
            const startTime = performance.now();

            function easeInOutCubic(t) {
                return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
            }

            function animate(now) {
                const elapsed = now - startTime;
                const progress = Math.min(elapsed / durationMs, 1);
                const eased = easeInOutCubic(progress);

                const x = startX + (targetX - startX) * eased;
                const y = startY + (targetY - startY) * eased;

                cursor.style.transform = `translate(${x}px, ${y}px)`;
                window.__cursorX = x;
                window.__cursorY = y;

                if (progress < 1) {
                    requestAnimationFrame(animate);
                } else {
                    resolve();
                }
            }
            requestAnimationFrame(animate);
        });
    };
}
"""


class BrowserScreenShare:
    """Manages a headless browser and publishes its screen as a LiveKit video track."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._source: rtc.VideoSource | None = None
        self._running = False
        self._capture_task: asyncio.Task | None = None
        self._page_lock = asyncio.Lock()
        self._last_good_frame: rtc.VideoFrame | None = None
        # Track cursor position so it persists across page navigations
        self._cursor_x: float = VIEWPORT_WIDTH / 2
        self._cursor_y: float = VIEWPORT_HEIGHT / 2

    @property
    def page(self) -> Page | None:
        return self._page

    async def _find_element_with_fallback(self, selector: str) -> Locator | None:
        """Multi-tier fallback to find an element. Caller must hold _page_lock.

        Priority order (most → least reliable):
        1. Role-based: get_by_role("link"|"button"|"menuitem"|"tab", name=selector)
        2. Exact text: get_by_text(selector, exact=True)
        3. Substring text: get_by_text(selector, exact=False)
        4. CSS selector: page.locator(selector)
        5. Text extracted from pseudo-selectors: :has-text, :contains, text=
        6. Aria-label: get_by_label(selector)
        Returns the first Locator that resolves to a visible element, or None.
        """
        if not self._page:
            return None

        # Tier 1: role-based matching (Playwright's most resilient strategy)
        for role in ("link", "button", "menuitem", "tab"):
            try:
                loc = self._page.get_by_role(role, name=selector)
                count = await loc.count()
                if count == 1:
                    box = await loc.bounding_box(timeout=2000)
                    if box:
                        logger.info(f"Found element by role '{role}' name '{selector}'")
                        return loc
                elif count > 1:
                    # Multiple matches — try the first visible one
                    loc = loc.first
                    box = await loc.bounding_box(timeout=2000)
                    if box:
                        logger.info(f"Found element by role '{role}' name '{selector}' (first of {count})")
                        return loc
            except Exception:
                pass

        # Tier 2: exact text match
        try:
            loc = self._page.get_by_text(selector, exact=True).first
            box = await loc.bounding_box(timeout=2000)
            if box:
                logger.info(f"Found element by exact text '{selector}'")
                return loc
        except Exception:
            pass

        # Tier 3: substring text match
        try:
            loc = self._page.get_by_text(selector, exact=False).first
            box = await loc.bounding_box(timeout=2000)
            if box:
                logger.info(f"Found element by substring text '{selector}'")
                return loc
        except Exception:
            pass

        # Tier 4: CSS selector (for backward compatibility)
        sanitized = sanitize_selector(selector)
        try:
            loc = self._page.locator(sanitized).first
            box = await loc.bounding_box(timeout=2000)
            if box:
                logger.info(f"Found element by CSS selector '{sanitized}'")
                return loc
        except Exception:
            pass

        # Tier 5: text extracted from pseudo-selectors
        text = _extract_text_from_selector(selector)
        if text and text != selector:
            try:
                loc = self._page.get_by_text(text, exact=False).first
                box = await loc.bounding_box(timeout=2000)
                if box:
                    logger.info(f"Found element by extracted text '{text}' from selector '{selector}'")
                    return loc
            except Exception:
                pass

        # Tier 6: aria-label matching
        label = _extract_aria_label(selector)
        if label:
            try:
                loc = self._page.get_by_label(label).first
                box = await loc.bounding_box(timeout=2000)
                if box:
                    logger.info(f"Found element by aria-label '{label}'")
                    return loc
            except Exception:
                pass

        logger.warning(f"All fallbacks failed for selector: {selector}")
        return None

    async def scan_interactive_elements(self) -> dict:
        """Scan the current page for all visible interactive elements.

        Returns a dict with categorized elements extracted from the live DOM.
        Each element has: text, href (if link), role, and position info.
        """
        if not self._page:
            return {"nav_links": [], "buttons": [], "other_links": [], "inputs": []}

        async with self._page_lock:
            raw = await self._page.evaluate("""
                () => {
                    // Helper: is element visible?
                    function isVisible(el) {
                        if (!el.offsetParent && el.tagName !== 'BODY') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    }

                    // Helper: is element inside a <nav> or has nav-like role?
                    function isInNav(el) {
                        let node = el;
                        while (node) {
                            if (node.tagName === 'NAV') return true;
                            if (node.getAttribute && node.getAttribute('role') === 'navigation') return true;
                            node = node.parentElement;
                        }
                        return false;
                    }

                    const results = {nav_links: [], buttons: [], other_links: [], inputs: []};

                    // Collect all links
                    for (const a of document.querySelectorAll('a[href]')) {
                        if (!isVisible(a)) continue;
                        const text = (a.innerText || a.getAttribute('aria-label') || '').trim();
                        if (!text) continue;
                        const entry = {
                            text: text.substring(0, 80),
                            href: a.href,
                            path: new URL(a.href, location.origin).pathname,
                            aria_label: a.getAttribute('aria-label') || null,
                        };
                        if (isInNav(a)) {
                            results.nav_links.push(entry);
                        } else {
                            results.other_links.push(entry);
                        }
                    }

                    // Collect all buttons
                    const btnSelectors = 'button, [role="button"], input[type="submit"], input[type="button"]';
                    for (const btn of document.querySelectorAll(btnSelectors)) {
                        if (!isVisible(btn)) continue;
                        const text = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim();
                        if (!text) continue;
                        results.buttons.push({
                            text: text.substring(0, 80),
                            aria_label: btn.getAttribute('aria-label') || null,
                        });
                    }

                    // Collect inputs (for context — not clickable but good to know about)
                    for (const inp of document.querySelectorAll('input[type="text"], input[type="email"], input[type="search"], textarea')) {
                        if (!isVisible(inp)) continue;
                        const label = inp.getAttribute('aria-label') || inp.getAttribute('placeholder') || '';
                        if (label) {
                            results.inputs.push({text: label.substring(0, 80)});
                        }
                    }

                    return results;
                }
            """)
        return raw

    async def start(self, room: rtc.Room, url: str):
        """Launch browser, navigate to URL, and start publishing screen share."""
        logger.info(f"Starting browser screen share for {url}")

        # Launch Playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
        )

        # Re-inject cursor automatically after any full page load (covers site-initiated navigations)
        self._page.on("load", lambda _: asyncio.ensure_future(self._inject_cursor()))

        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self._inject_cursor()
        logger.info(f"Browser navigated to {url}")

        # Create video source and publish as screen share track
        self._source = rtc.VideoSource(VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
        track = rtc.LocalVideoTrack.create_video_track("browser-screen", self._source)
        options = rtc.TrackPublishOptions(
            source=rtc.TrackSource.SOURCE_SCREENSHARE,
        )
        await room.local_participant.publish_track(track, options)
        logger.info("Screen share track published")

        # Start capture loop
        self._running = True
        self._capture_task = asyncio.create_task(self._capture_loop())

    @staticmethod
    def _decode_frame(screenshot_bytes: bytes) -> rtc.VideoFrame:
        """CPU-bound: decode JPEG and convert to RGBA VideoFrame. Runs in thread pool."""
        img = Image.open(io.BytesIO(screenshot_bytes)).convert("RGBA")
        if img.size != (VIEWPORT_WIDTH, VIEWPORT_HEIGHT):
            img = img.resize((VIEWPORT_WIDTH, VIEWPORT_HEIGHT))
        frame_data = np.array(img)
        return rtc.VideoFrame(
            width=VIEWPORT_WIDTH,
            height=VIEWPORT_HEIGHT,
            type=rtc.VideoBufferType.RGBA,
            data=frame_data.tobytes(),
        )

    async def _capture_loop(self):
        """Continuously capture browser screenshots and push to video source."""
        interval = 1.0 / TARGET_FPS
        loop = asyncio.get_event_loop()
        while self._running:
            frame_start = loop.time()
            try:
                async with self._page_lock:
                    screenshot_bytes = await self._page.screenshot(type="jpeg", quality=65)
                frame = await loop.run_in_executor(
                    None, self._decode_frame, screenshot_bytes
                )
                self._source.capture_frame(frame)
                self._last_good_frame = frame
            except Exception as e:
                logger.error(f"Screen capture error: {e}")
                if self._last_good_frame is not None:
                    self._source.capture_frame(self._last_good_frame)

            elapsed = loop.time() - frame_start
            await asyncio.sleep(max(0.0, interval - elapsed))

    async def _inject_cursor(self):
        """Inject the custom cursor overlay into the current page at the stored position."""
        if self._page:
            try:
                await self._page.evaluate(CURSOR_INJECT_JS, [self._cursor_x, self._cursor_y])
            except Exception as e:
                logger.warning(f"Could not inject cursor: {e}")

    async def _start_cursor_animation(self, locator_or_selector, duration_ms: int = 500):
        """Start cursor animation toward an element. Caller must hold _page_lock.

        Accepts either a Locator (already resolved) or a string selector (will use fallback).
        Returns (duration_to_wait, resolved_locator) or (0, None) if animation couldn't start.
        """
        if not self._page:
            return 0, None

        try:
            if isinstance(locator_or_selector, str):
                locator = await self._find_element_with_fallback(locator_or_selector)
            else:
                locator = locator_or_selector

            if not locator:
                return 0, None

            box = await locator.bounding_box(timeout=3000)
            if box:
                target_x = box["x"] + box["width"] / 2
                target_y = box["y"] + box["height"] / 2
                # Save cursor destination so it persists across page navigations
                self._cursor_x = target_x
                self._cursor_y = target_y
                await self._page.evaluate(
                    f"void(window.__moveCursorTo && window.__moveCursorTo({target_x}, {target_y}, {duration_ms}))"
                )
                return duration_ms, locator
        except Exception as e:
            logger.warning(f"Could not start cursor animation to {locator_or_selector}: {e}")
        return 0, None

    async def navigate(self, url: str):
        """Navigate browser to a new URL."""
        if self._page:
            async with self._page_lock:
                await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self._inject_cursor()
            logger.info(f"Navigated to {url}")

    async def click(self, selector: str):
        """Move cursor to element smoothly, then click it using fallback resolution."""
        if self._page:
            # Phase 1: resolve element and start cursor animation (brief lock)
            async with self._page_lock:
                await self._inject_cursor()
                duration, locator = await self._start_cursor_animation(selector, duration_ms=700)

            if locator is None:
                raise Exception(
                    f"Could not find element '{selector}' after trying CSS, text, "
                    "and aria-label matching. Try a simpler selector or skip to the next step."
                )

            # Phase 2: wait for animation WITHOUT holding the lock
            if duration > 0:
                await asyncio.sleep(duration / 1000 + 0.05)

            # Phase 3: perform the actual click via the resolved locator (brief lock)
            async with self._page_lock:
                await locator.click(timeout=5000)
            logger.info(f"Clicked {selector}")

    async def scroll_down(self, pixels: int = 400):
        """Scroll down the page with a smooth animation."""
        if self._page:
            duration_ms = max(400, min(1200, pixels * 2))  # scale with distance, 400-1200ms

            # Phase 1: start smooth scroll animation (fire-and-forget), then release lock
            async with self._page_lock:
                await self._inject_cursor()
                await self._page.evaluate(
                    f"void(window.__smoothScrollBy && window.__smoothScrollBy({pixels}, {duration_ms}))"
                )

            # Phase 2: let capture loop record the smooth scroll
            await asyncio.sleep(duration_ms / 1000 + 0.05)

    async def scroll_to_element(self, selector: str):
        """Scroll to bring an element into view smoothly, then move cursor to it."""
        if self._page:
            # Phase 1: resolve element, calculate scroll distance, start smooth scroll
            scroll_duration_ms = 0
            locator = None
            async with self._page_lock:
                await self._inject_cursor()
                locator = await self._find_element_with_fallback(selector)
                if locator:
                    try:
                        box = await locator.bounding_box(timeout=3000)
                        if box:
                            target_center_y = box["y"] + box["height"] / 2
                            viewport_center = VIEWPORT_HEIGHT / 2
                            delta = target_center_y - viewport_center
                            if abs(delta) > 50:
                                scroll_duration_ms = max(400, min(1200, int(abs(delta) * 2)))
                                await self._page.evaluate(
                                    f"void(window.__smoothScrollBy && window.__smoothScrollBy({delta}, {scroll_duration_ms}))"
                                )
                    except Exception as e:
                        logger.warning(f"Could not calculate scroll for {selector}: {e}")
                        try:
                            await locator.scroll_into_view_if_needed(timeout=5000)
                        except Exception:
                            pass

            if locator is None:
                raise Exception(
                    f"Could not find element '{selector}' after trying CSS, text, "
                    "and aria-label matching. Try a simpler selector or skip to the next step."
                )

            # Phase 2: wait for scroll animation
            if scroll_duration_ms > 0:
                await asyncio.sleep(scroll_duration_ms / 1000 + 0.05)

            # Phase 3: animate cursor to the already-resolved element
            async with self._page_lock:
                await self._inject_cursor()
                cursor_duration, _ = await self._start_cursor_animation(locator, duration_ms=600)

            if cursor_duration > 0:
                await asyncio.sleep(cursor_duration / 1000 + 0.05)

    async def highlight_element(self, selector: str):
        """Move cursor to element, then add a visual highlight around it."""
        if self._page:
            # Phase 1: resolve element and start cursor animation
            async with self._page_lock:
                await self._inject_cursor()
                duration, locator = await self._start_cursor_animation(selector, duration_ms=600)

            if locator is None:
                logger.warning(f"Could not highlight element: {selector}")
                return

            # Phase 2: wait for animation WITHOUT holding lock
            if duration > 0:
                await asyncio.sleep(duration / 1000 + 0.05)

            # Phase 3: apply the highlight via the resolved locator (bypasses querySelector)
            async with self._page_lock:
                await locator.evaluate("""
                    (el) => {
                        el.style.outline = '3px solid #FF6B00';
                        el.style.outlineOffset = '2px';
                        setTimeout(() => {
                            el.style.outline = '';
                            el.style.outlineOffset = '';
                        }, 3000);
                    }
                """)

    async def get_page_content(self) -> str:
        """Get visible text content of the current page."""
        if self._page:
            async with self._page_lock:
                return await self._page.evaluate("document.body.innerText")
        return ""

    async def get_current_url(self) -> str:
        if self._page:
            return self._page.url
        return ""

    async def stop(self):
        """Clean up browser and stop capture."""
        self._running = False
        if self._capture_task:
            self._capture_task.cancel()
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Cleanup error (non-fatal): {e}")
        logger.info("Screen share stopped")
