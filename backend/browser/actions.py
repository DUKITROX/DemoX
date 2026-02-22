import asyncio
from typing import Callable, Optional, Awaitable

import backend.browser.controller as _controller
from backend.browser.controller import get_current_page, move_cursor_to


CursorCallback = Optional[Callable[[int, int], Awaitable[None]]]

# Key name mapping: Claude Computer Use -> Playwright
_KEY_MAP = {
    "Return": "Enter",
    "BackSpace": "Backspace",
    "space": " ",
}

_MODIFIER_MAP = {
    "ctrl": "Control",
    "alt": "Alt",
    "shift": "Shift",
    "meta": "Meta",
    "super": "Meta",
    "cmd": "Meta",
}


def _map_key_combo(combo: str) -> str:
    """Map Claude CU key names to Playwright key names."""
    combo = _KEY_MAP.get(combo, combo)

    if "+" in combo:
        parts = combo.split("+")
        mapped = [_MODIFIER_MAP.get(p.lower(), p) for p in parts]
        return "+".join(mapped)

    return combo


def get_action_coordinate(action_data: dict) -> tuple[int, int] | None:
    """Extract the target coordinate from an action, if it has one."""
    coordinate = action_data.get("coordinate")
    if coordinate and len(coordinate) == 2:
        return (int(coordinate[0]), int(coordinate[1]))
    return None


async def _emit_cursor_path(
    start_x: int, start_y: int,
    end_x: int, end_y: int,
    on_cursor_move: CursorCallback,
    steps: int = 6,
):
    """Emit intermediate cursor positions along a path with smoothstep easing."""
    if not on_cursor_move:
        return
    for i in range(1, steps + 1):
        t = i / steps
        # Smoothstep (cubic ease-in-out) for natural movement
        t_eased = t * t * (3 - 2 * t)
        ix = int(start_x + (end_x - start_x) * t_eased)
        iy = int(start_y + (end_y - start_y) * t_eased)
        await on_cursor_move(ix, iy)
        await asyncio.sleep(0.05)


async def execute_computer_action(action_data: dict, on_cursor_move: CursorCallback = None) -> None:
    """
    Execute a coordinate-based action from Claude Computer Use.

    Supported actions: left_click, right_click, double_click, middle_click,
    mouse_move, type, key, scroll, left_click_drag, cursor_position, screenshot.
    """
    page = get_current_page()
    if not page:
        raise RuntimeError("Browser not started")

    action = action_data.get("action")
    coordinate = action_data.get("coordinate")
    text = action_data.get("text")

    if action == "left_click":
        x, y = coordinate
        await _emit_cursor_path(_controller._last_cursor_x, _controller._last_cursor_y, x, y, on_cursor_move)
        await page.mouse.move(x, y, steps=20)
        await move_cursor_to(x, y)
        await asyncio.sleep(0.10)
        await page.mouse.click(x, y)
        await asyncio.sleep(0.20)

    elif action == "right_click":
        x, y = coordinate
        await _emit_cursor_path(_controller._last_cursor_x, _controller._last_cursor_y, x, y, on_cursor_move)
        await page.mouse.move(x, y, steps=20)
        await move_cursor_to(x, y)
        await asyncio.sleep(0.10)
        await page.mouse.click(x, y, button="right")
        await asyncio.sleep(0.20)

    elif action == "double_click":
        x, y = coordinate
        await _emit_cursor_path(_controller._last_cursor_x, _controller._last_cursor_y, x, y, on_cursor_move)
        await page.mouse.move(x, y, steps=20)
        await move_cursor_to(x, y)
        await asyncio.sleep(0.10)
        await page.mouse.dblclick(x, y)
        await asyncio.sleep(0.20)

    elif action == "middle_click":
        x, y = coordinate
        await _emit_cursor_path(_controller._last_cursor_x, _controller._last_cursor_y, x, y, on_cursor_move)
        await page.mouse.move(x, y, steps=20)
        await move_cursor_to(x, y)
        await asyncio.sleep(0.10)
        await page.mouse.click(x, y, button="middle")
        await asyncio.sleep(0.20)

    elif action == "mouse_move":
        x, y = coordinate
        await _emit_cursor_path(_controller._last_cursor_x, _controller._last_cursor_y, x, y, on_cursor_move)
        await page.mouse.move(x, y, steps=20)
        await move_cursor_to(x, y)
        await asyncio.sleep(0.1)

    elif action == "type":
        await page.keyboard.type(text, delay=50)
        await asyncio.sleep(0.2)

    elif action == "key":
        combo = _map_key_combo(text)
        await page.keyboard.press(combo)
        await asyncio.sleep(0.2)

    elif action == "scroll":
        x, y = coordinate or (640, 400)
        direction = action_data.get("scroll_direction", "down")
        amount = action_data.get("scroll_amount", 3)
        pixels = amount * 100
        if direction in ("up", "left"):
            pixels = -pixels

        await _emit_cursor_path(_controller._last_cursor_x, _controller._last_cursor_y, x, y, on_cursor_move)
        await page.mouse.move(x, y, steps=5)
        await move_cursor_to(x, y)
        if direction in ("up", "down"):
            await page.mouse.wheel(0, pixels)
        else:
            await page.mouse.wheel(pixels, 0)
        await asyncio.sleep(0.30)

    elif action == "left_click_drag":
        start = action_data.get("start_coordinate", coordinate)
        end = coordinate
        sx, sy = start
        ex, ey = end
        await _emit_cursor_path(_controller._last_cursor_x, _controller._last_cursor_y, sx, sy, on_cursor_move)
        await page.mouse.move(sx, sy, steps=15)
        await move_cursor_to(sx, sy)
        await asyncio.sleep(0.1)
        await page.mouse.down()
        await _emit_cursor_path(sx, sy, ex, ey, on_cursor_move, steps=8)
        await page.mouse.move(ex, ey, steps=20)
        await move_cursor_to(ex, ey)
        await page.mouse.up()
        await asyncio.sleep(0.35)

    elif action == "wait":
        duration = action_data.get("duration", 2)
        duration = max(0.5, min(duration, 5))
        await asyncio.sleep(duration)

    elif action in ("cursor_position", "screenshot"):
        # No browser action needed — just return so caller can take screenshot
        pass

    else:
        raise ValueError(f"Unknown computer use action: {action}")
