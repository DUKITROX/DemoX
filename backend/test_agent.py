import asyncio
import logging
import base64
import io
import os
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from backend.agent.computer_use import run_computer_use_loop
from backend.agent.state import SessionState
from backend.browser.controller import start_browser, take_screenshot, close_browser

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("Interactive-Test")


async def save_debug_image(b64_string: str, filename: str):
    """Saves the Base64 screenshot to disk."""
    if not b64_string:
        return
    image_data = base64.b64decode(b64_string)
    image = Image.open(io.BytesIO(image_data))
    image.save(filename)
    logger.info(f"Screenshot saved: {filename}")


async def run_interactive_chat():
    logger.info("Starting Playwright and loading monkeytype.com...")

    await start_browser(start_url="https://monkeytype.com")

    session = SessionState(session_id="test-session")

    step_counter = 1
    print("\n" + "=" * 50)
    print("INTERACTIVE DEMO TEST")
    print("  Type 'exit' or 'quit' to end the session.")
    print("  Try: 'Show me the dashboard', 'Click on Products', 'What is this platform?'")
    print("=" * 50 + "\n")

    while True:
        user_input = input("\nYou: ")

        if user_input.lower().strip() in ["exit", "quit"]:
            logger.info("Ending test...")
            await close_browser()
            print("\nSession ended.\n")
            break

        if not user_input.strip():
            continue

        # Take 'before' screenshot
        before = await take_screenshot()
        await save_debug_image(before, f"step_{step_counter}_before.png")

        # Run the agent
        logger.info("Agent is processing...")

        async def print_text(text: str):
            pass  # collect silently, print full response after

        async def print_action(action: str):
            print(f"  [Action: {action}]")

        async def save_screenshot(b64: str):
            await save_debug_image(b64, f"step_{step_counter}_action.png")

        response = await run_computer_use_loop(
            session=session,
            user_message=user_input,
            on_text_delta=print_text,
            on_tool_action=print_action,
            on_screenshot=save_screenshot,
        )

        print(f"\nAgent: {response}")

        # Take 'after' screenshot
        after = await take_screenshot()
        await save_debug_image(after, f"step_{step_counter}_after.png")

        step_counter += 1


if __name__ == "__main__":
    asyncio.run(run_interactive_chat())
