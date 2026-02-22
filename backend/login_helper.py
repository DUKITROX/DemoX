#!/usr/bin/env python3
"""
One-time login helper: opens a VISIBLE browser window so you can log in manually.
Saves auth_state.json for all future headless sessions.

Usage:
    cd backend && python login_helper.py
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from playwright.async_api import async_playwright

AUTH_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "auth_state.json")
DEMO_URL = os.getenv("DEMO_START_URL", "https://monkeytype.com")


async def main():
    print(f"Opening {DEMO_URL} in a visible browser window...")
    print("Please log in manually. Once you see the dashboard, press Enter here.")
    print()

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)

    context_kwargs = {"viewport": {"width": 1280, "height": 800}}
    if os.path.exists(AUTH_STATE_FILE):
        context_kwargs["storage_state"] = AUTH_STATE_FILE
        print(f"(Loading existing auth state from {AUTH_STATE_FILE})")

    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()
    await page.goto(DEMO_URL, wait_until="domcontentloaded", timeout=30000)

    # Try auto-login with env vars first
    email = os.getenv("DEMO_LOGIN_EMAIL", "").strip()
    password = os.getenv("DEMO_LOGIN_PASSWORD", "").strip()

    if email and password:
        print(f"Attempting auto-login with {email}...")
        try:
            # Check for Google sign-in button
            google_btn = page.locator(
                "button:has-text('Sign in with Google'), "
                "button:has-text('Continue with Google'), "
                "a:has-text('Sign in with Google'), "
                "a:has-text('Continue with Google')"
            ).first
            try:
                if await google_btn.is_visible(timeout=3000):
                    print("Found Google sign-in button. Clicking...")
                    async with page.context.expect_page(timeout=5000) as popup_info:
                        await google_btn.click()
                    popup = await popup_info.value
                    await popup.wait_for_load_state("domcontentloaded")

                    # Fill Google email
                    email_input = popup.locator("input[type='email']").first
                    await email_input.wait_for(state="visible", timeout=8000)
                    await email_input.fill(email)
                    await popup.locator("#identifierNext, button:has-text('Next')").first.click()
                    await asyncio.sleep(3)

                    # Fill Google password
                    pwd_input = popup.locator("input[type='password']").first
                    await pwd_input.wait_for(state="visible", timeout=8000)
                    await pwd_input.fill(password)
                    await popup.locator("#passwordNext, button:has-text('Next')").first.click()
                    await asyncio.sleep(5)

                    print("Google login submitted. Waiting for redirect...")
                    await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                print(f"Google OAuth attempt: {e}")

            # Check for direct email/password form
            email_field = page.locator("input[type='email'], input[name='email']").first
            pwd_field = page.locator("input[type='password'], input[name='password']").first
            try:
                if await email_field.is_visible(timeout=2000) and await pwd_field.is_visible(timeout=2000):
                    await email_field.fill(email)
                    await pwd_field.fill(password)
                    submit = page.locator(
                        "button[type='submit'], button:has-text('Sign in'), "
                        "button:has-text('Log in'), button:has-text('Continue')"
                    ).first
                    if await submit.is_visible(timeout=2000):
                        await submit.click()
                        await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
        except Exception as e:
            print(f"Auto-login failed: {e}")

    # Wait for user confirmation
    print()
    print("=" * 60)
    print("If you're logged in and see the dashboard, press Enter to save.")
    print("If not, log in manually in the browser window, then press Enter.")
    print("=" * 60)
    await asyncio.get_event_loop().run_in_executor(None, input)

    # Save auth state
    await context.storage_state(path=AUTH_STATE_FILE)
    print(f"\nAuth state saved to {AUTH_STATE_FILE}")
    print("Future runs will be automatically logged in.")

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
