import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        print("=== Step 1: Navigating to URL ===")
        try:
            await page.goto("https://metric-master-suite505.apps.rebolt.ai/", wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"Navigation warning: {e}")
            # Try with domcontentloaded fallback
            try:
                await page.goto("https://metric-master-suite505.apps.rebolt.ai/", wait_until="domcontentloaded", timeout=30000)
            except:
                pass

        print(f"Current URL: {page.url}")
        print(f"Page title: {await page.title()}")

        # Wait a bit for any JS rendering
        await page.wait_for_timeout(3000)

        print("\n=== Step 2: Taking screenshot 1 ===")
        await page.screenshot(path="/Users/danielbordeianu/git/DemoX/debug_screenshot_1.png", full_page=True)
        print("Saved debug_screenshot_1.png")

        print("\n=== Step 3: Finding input fields and buttons ===")
        # Find all input fields
        inputs = await page.query_selector_all("input")
        print(f"Found {len(inputs)} input elements:")
        for i, inp in enumerate(inputs):
            inp_type = await inp.get_attribute("type") or "text"
            inp_name = await inp.get_attribute("name") or ""
            inp_placeholder = await inp.get_attribute("placeholder") or ""
            inp_id = await inp.get_attribute("id") or ""
            is_visible = await inp.is_visible()
            print(f"  [{i}] type={inp_type}, name={inp_name}, id={inp_id}, placeholder={inp_placeholder}, visible={is_visible}")

        # Find all buttons
        buttons = await page.query_selector_all("button")
        print(f"\nFound {len(buttons)} button elements:")
        for i, btn in enumerate(buttons):
            btn_text = (await btn.inner_text()).strip()
            btn_type = await btn.get_attribute("type") or ""
            is_visible = await btn.is_visible()
            print(f"  [{i}] text='{btn_text}', type={btn_type}, visible={is_visible}")

        # Also check for links that might look like buttons
        links = await page.query_selector_all("a")
        print(f"\nFound {len(links)} link elements:")
        for i, link in enumerate(links):
            link_text = (await link.inner_text()).strip()
            href = await link.get_attribute("href") or ""
            is_visible = await link.is_visible()
            if is_visible and link_text:
                print(f"  [{i}] text='{link_text}', href={href}")

        print("\n=== Step 4: Filling email and password ===")
        try:
            # Try multiple strategies to find email field
            email_filled = False
            for selector in [
                'input[type="email"]',
                'input[name="email"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="Email"]',
                'input[id*="email" i]',
                'input[type="text"]',
            ]:
                els = await page.query_selector_all(selector)
                for el in els:
                    if await el.is_visible():
                        await el.fill("dunkito4president@gmail.com")
                        print(f"Filled email using selector: {selector}")
                        email_filled = True
                        break
                if email_filled:
                    break

            if not email_filled:
                print("WARNING: Could not find email field")

            # Try multiple strategies to find password field
            pwd_filled = False
            for selector in [
                'input[type="password"]',
                'input[name="password"]',
                'input[placeholder*="password" i]',
                'input[placeholder*="Password"]',
                'input[id*="password" i]',
            ]:
                els = await page.query_selector_all(selector)
                for el in els:
                    if await el.is_visible():
                        await el.fill("sywmot-kyshYj-9fowku")
                        print(f"Filled password using selector: {selector}")
                        pwd_filled = True
                        break
                if pwd_filled:
                    break

            if not pwd_filled:
                print("WARNING: Could not find password field")

        except Exception as e:
            print(f"Error filling fields: {e}")

        print("\n=== Step 5: Taking screenshot 2 (after fill) ===")
        await page.screenshot(path="/Users/danielbordeianu/git/DemoX/debug_screenshot_2.png", full_page=True)
        print("Saved debug_screenshot_2.png")

        print("\n=== Step 6: Clicking Sign In button ===")
        try:
            # Try multiple strategies
            clicked = False
            for strategy_name, locator in [
                ("get_by_role button 'Sign In'", page.get_by_role("button", name="Sign In")),
                ("get_by_role button 'Sign in'", page.get_by_role("button", name="Sign in")),
                ("get_by_role button 'Log In'", page.get_by_role("button", name="Log In")),
                ("get_by_role button 'Log in'", page.get_by_role("button", name="Log in")),
                ("get_by_role button 'Login'", page.get_by_role("button", name="Login")),
                ("get_by_role button 'Submit'", page.get_by_role("button", name="Submit")),
                ("get_by_text 'Sign In'", page.get_by_text("Sign In")),
                ("get_by_text 'Sign in'", page.get_by_text("Sign in")),
                ("get_by_text 'Log in'", page.get_by_text("Log in")),
            ]:
                try:
                    if await locator.count() > 0 and await locator.first.is_visible():
                        await locator.first.click()
                        print(f"Clicked using: {strategy_name}")
                        clicked = True
                        break
                except:
                    continue

            if not clicked:
                # Fallback: click first visible submit/button
                for selector in ['button[type="submit"]', "button"]:
                    els = await page.query_selector_all(selector)
                    for el in els:
                        if await el.is_visible():
                            text = (await el.inner_text()).strip()
                            await el.click()
                            print(f"Clicked button with text '{text}' using selector: {selector}")
                            clicked = True
                            break
                    if clicked:
                        break

            if not clicked:
                print("WARNING: Could not find any sign-in button to click")

        except Exception as e:
            print(f"Error clicking sign in: {e}")

        print("\n=== Step 7: Waiting for navigation ===")
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Navigation wait warning: {e}")

        await page.wait_for_timeout(3000)

        print("\n=== Step 8: Taking screenshot 3 (after login attempt) ===")
        await page.screenshot(path="/Users/danielbordeianu/git/DemoX/debug_screenshot_3.png", full_page=True)
        print("Saved debug_screenshot_3.png")

        print(f"\n=== Final URL: {page.url} ===")
        print(f"=== Page title: {await page.title()} ===")

        # Check for any error messages
        print("\n=== Checking for error messages ===")
        body_text = await page.inner_text("body")
        for keyword in ["error", "invalid", "incorrect", "failed", "wrong", "denied"]:
            lines = [line.strip() for line in body_text.split("\n") if keyword.lower() in line.lower() and line.strip()]
            for line in lines[:3]:
                print(f"  Found '{keyword}': {line[:200]}")

        # Print page HTML structure for debugging if login seems to have failed
        if "login" in page.url.lower() or "signin" in page.url.lower() or "sign-in" in page.url.lower():
            print("\n=== Still on login page - dumping body HTML snippet ===")
            html = await page.content()
            # Print first 3000 chars of body
            import re
            body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
            if body_match:
                print(body_match.group(1)[:3000])

        await browser.close()

asyncio.run(main())
