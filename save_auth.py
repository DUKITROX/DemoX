"""One-time helper: opens a visible browser so you can log in manually.
Saves cookies + localStorage to auth_state.json for Playwright to reuse.

Uses persistent_context to avoid --enable-automation flag that Google detects.

Usage:
    .venv/bin/python save_auth.py https://usetalky.com/invoices
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

AUTH_STATE_FILE = "auth_state.json"
PROFILE_DIR = os.path.join(os.path.dirname(__file__), ".chrome_profile")


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://usetalky.com"

    pw = await async_playwright().start()

    # launch_persistent_context avoids the --enable-automation flag
    # that Google uses to detect and block automated browsers
    context = await pw.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=False,
        channel="chrome",
        viewport={"width": 1280, "height": 720},
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
    )

    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(url, wait_until="domcontentloaded")

    print(f"\n>>> Browser opened at {url}")
    print(">>> Log in with Google (or however you need to).")
    print(">>> When you're fully logged in, come back here and press ENTER to save.\n")

    await asyncio.get_event_loop().run_in_executor(None, input)

    await context.storage_state(path=AUTH_STATE_FILE)
    print(f"Auth state saved to {AUTH_STATE_FILE}")

    await context.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
