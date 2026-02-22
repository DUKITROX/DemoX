import asyncio
import os
import base64
import logging
from playwright.async_api import async_playwright, Page, BrowserContext

# Global variables to keep the browser session alive on the server
_playwright_instance = None
_browser = None
_context: BrowserContext = None
_page: Page = None

# Track last known cursor position so we can re-position after re-injection
_last_cursor_x = 640
_last_cursor_y = 400

AUTH_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "auth_state.json")
logger = logging.getLogger(__name__)

# The cursor injection JS, extracted so we can re-inject on every navigation
_CURSOR_JS = """
() => {
    if (document.getElementById('ai-cursor')) return;

    const cursorArrow = "url(\\"data:image/svg+xml,%3Csvg width='24' height='24' viewBox='0 0 24 24' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M5.5 3.21V20.8L9.6 16.7L12.5 22.8L15.3 21.4L12.4 15.3H18.6L5.5 3.21Z' fill='black' stroke='white' stroke-width='1.5' stroke-linejoin='round'/%3E%3C/svg%3E\\")";

    const cursorHand = "url(\\"data:image/svg+xml,%3Csvg width='24' height='24' viewBox='0 0 24 24' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M10.5 10.5V3.5C10.5 2.4 11.5 2.4 11.5 3.5V10.5M11.5 10.5V5.5C11.5 4.4 12.5 4.4 12.5 5.5V10.5M12.5 10.5V6.5C12.5 5.4 13.5 5.4 13.5 6.5V10.5M13.5 10.5V8.5C13.5 7.4 14.5 7.4 14.5 8.5V14.5C14.5 18.5 11.5 21.5 8.5 21.5H7.5C4.5 21.5 2.5 18.5 2.5 14.5V11.5C2.5 10.4 3.5 10.4 3.5 11.5V13.5M10.5 10.5L6.5 6.5' fill='black' stroke='white' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\\")";

    const cursor = document.createElement('div');
    cursor.id = 'ai-cursor';
    cursor.style.width = '24px';
    cursor.style.height = '24px';
    cursor.style.position = 'fixed';
    cursor.style.zIndex = '2147483647';
    cursor.style.pointerEvents = 'none';
    cursor.style.backgroundImage = cursorArrow;
    cursor.style.backgroundSize = 'contain';
    cursor.style.backgroundRepeat = 'no-repeat';
    cursor.style.transition = 'left 0.08s linear, top 0.08s linear';
    cursor.style.left = '640px';
    cursor.style.top = '400px';
    document.body.appendChild(cursor);

    // Hide the real cursor so only our fake one shows
    const style = document.createElement('style');
    style.textContent = '* { cursor: none !important; }';
    document.head.appendChild(style);

    document.addEventListener('mousemove', (e) => {
        cursor.style.left = e.clientX + 'px';
        cursor.style.top = e.clientY + 'px';

        const elementUnderCursor = document.elementFromPoint(e.clientX, e.clientY);
        let isClickable = false;

        if (elementUnderCursor) {
            const computedStyle = window.getComputedStyle(elementUnderCursor);
            if (
                computedStyle.cursor === 'pointer' ||
                elementUnderCursor.tagName.toLowerCase() === 'a' ||
                elementUnderCursor.tagName.toLowerCase() === 'button' ||
                elementUnderCursor.closest('a, button, [role="button"], [onclick]') !== null
            ) {
                isClickable = true;
            }
        }

        cursor.style.backgroundImage = isClickable ? cursorHand : cursorArrow;
    });
}
"""


async def start_browser(start_url: str) -> Page:
    """Starts the headless browser and prepares the demo environment."""
    global _playwright_instance, _browser, _context, _page

    _playwright_instance = await async_playwright().start()
    _browser = await _playwright_instance.chromium.launch(headless=True)

    context_kwargs = {
        "viewport": {"width": 1280, "height": 800},
        "device_scale_factor": 1,
    }

    # Load saved auth cookies if available
    if os.path.exists(AUTH_STATE_FILE):
        context_kwargs["storage_state"] = AUTH_STATE_FILE

    _context = await _browser.new_context(**context_kwargs)
    _page = await _context.new_page()

    # Re-inject cursor on every navigation (page load)
    _page.on("load", _on_page_load)

    await _page.goto(start_url, wait_until="domcontentloaded", timeout=30000)

    # Give the page a moment to settle, then inject cursor and dismiss popups
    await asyncio.sleep(1)
    await _inject_fake_cursor(_page)
    await asyncio.sleep(1)
    await _dismiss_popups(_page)

    return _page


def _on_page_load(page: Page):
    """Callback: re-inject fake cursor and dismiss popups after every page navigation."""
    asyncio.ensure_future(_on_page_load_async(page))


async def _on_page_load_async(page: Page):
    await _inject_fake_cursor(page)
    await asyncio.sleep(1)
    await _dismiss_popups(page)


async def save_auth_state():
    """Persist browser cookies/storage after successful login."""
    if _context:
        await _context.storage_state(path=AUTH_STATE_FILE)


_DISMISS_POPUPS_JS = """
() => {
    // Cookie consent / notification banners
    const selectors = [
        '.cookieConsent button',
        '#cookieConsent button',
        'button.acceptAll',
        'button.acceptCookies',
        '[data-testid="cookie-accept"]',
        '.cookie-popup button',
        '.notification .close',
        '.popupWrapper .close',
        '#bannerClose',
        '.modal .close',
    ];
    for (const sel of selectors) {
        try {
            const els = document.querySelectorAll(sel);
            els.forEach(el => el.click());
        } catch(e) {}
    }
    // Also try text-based matching for accept/got-it buttons
    const buttons = document.querySelectorAll('button, a.button, [role="button"]');
    for (const btn of buttons) {
        const text = (btn.textContent || '').trim().toLowerCase();
        if (text === 'accept' || text === 'accept all' || text === 'got it' || text === 'i accept' || text === 'ok') {
            try { btn.click(); } catch(e) {}
        }
    }
}
"""


async def _dismiss_popups(page: Page):
    """Dismiss cookie consent and notification popups."""
    try:
        await page.evaluate(_DISMISS_POPUPS_JS)
    except Exception:
        pass


async def _inject_fake_cursor(page: Page):
    """Inject the fake cursor element into the page."""
    try:
        await page.evaluate(_CURSOR_JS)
        # Position cursor at last known location
        await _update_cursor_position(page, _last_cursor_x, _last_cursor_y)
    except Exception as exc:
        logger.debug(f"Cursor injection skipped: {exc}")


async def _update_cursor_position(page: Page, x: int, y: int):
    """Directly update the fake cursor position via JS (for screenshots)."""
    global _last_cursor_x, _last_cursor_y
    _last_cursor_x = x
    _last_cursor_y = y
    try:
        await page.evaluate(f"""
            () => {{
                const cursor = document.getElementById('ai-cursor');
                if (cursor) {{
                    cursor.style.left = '{x}px';
                    cursor.style.top = '{y}px';
                }}
            }}
        """)
    except Exception:
        pass


async def move_cursor_to(x: int, y: int):
    """Move the fake cursor to a position (called before screenshots)."""
    if _page:
        await _update_cursor_position(_page, x, y)


def _normalize_url(url: str) -> str:
    """Ensure the URL has a protocol prefix."""
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


async def navigate_to(url: str) -> str:
    """Navigate the browser to a new URL and return a screenshot."""
    global _page
    if not _page:
        raise RuntimeError("Browser not started")
    url = _normalize_url(url)
    await _page.goto(url, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(1)
    await _inject_fake_cursor(_page)
    await asyncio.sleep(1)
    await _dismiss_popups(_page)
    return await take_screenshot()


def get_current_page() -> Page:
    """Returns the current tab so the tools can use it."""
    return _page


async def take_screenshot() -> str:
    """Takes a screenshot of the current page and returns it as Base64 PNG."""
    if not _page:
        return None
    # Hide the in-page fake cursor before capturing — the frontend renders
    # its own overlay cursor, so we don't want a duplicate in the image.
    try:
        await _page.evaluate("""
            () => {
                const c = document.getElementById('ai-cursor');
                if (c) c.style.display = 'none';
            }
        """)
    except Exception:
        pass
    screenshot_bytes = await _page.screenshot(type="jpeg", quality=80)
    # Restore the fake cursor after capturing (still needed for position tracking)
    try:
        await _page.evaluate("""
            () => {
                const c = document.getElementById('ai-cursor');
                if (c) c.style.display = '';
            }
        """)
    except Exception:
        pass
    return base64.b64encode(screenshot_bytes).decode("utf-8")


async def query_page_content(js_expression: str) -> str:
    """Execute a JavaScript expression on the current page and return the result as a string."""
    if not _page:
        return "Error: browser not started"
    try:
        result = await _page.evaluate(js_expression)
        return str(result)[:2000]
    except Exception as e:
        return f"Error: {str(e)}"


async def close_browser():
    """Gracefully shuts down the browser and Playwright."""
    global _playwright_instance, _browser, _context, _page
    if _browser:
        await _browser.close()
        _browser = None
    if _context:
        _context = None
    _page = None
    if _playwright_instance:
        await _playwright_instance.stop()
        _playwright_instance = None
