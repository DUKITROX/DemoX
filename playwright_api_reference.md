# Playwright Python Async API Reference

Comprehensive reference for the Playwright Python **async** API, focused on headless browser
control by an AI agent. Covers locator strategies, element inspection, accessibility tree,
page interaction, navigation/waiting, and enumerating clickable elements.

Official docs: https://playwright.dev/python/docs/

---

## Table of Contents

1. [Locator Strategies](#1-locator-strategies)
2. [Element Inspection](#2-element-inspection)
3. [Accessibility Tree](#3-accessibility-tree)
4. [Page Interaction](#4-page-interaction)
5. [Navigation and Waiting](#5-navigation-and-waiting)
6. [Enumerating Clickable Elements](#6-enumerating-clickable-elements)
7. [Frames and Iframes](#7-frames-and-iframes)
8. [Practical Patterns for AI Agents](#8-practical-patterns-for-ai-agents)

---

## 1. Locator Strategies

Locators are the core abstraction for finding elements. They are **lazy** (no DOM query until
an action is performed), **auto-waiting** (wait for the element to be actionable), and
**strict** (throw if more than one element matches, unless you opt out with `.first`,
`.last`, `.nth()`).

### 1.1 Role-Based Locators (Recommended)

`page.get_by_role()` uses ARIA roles and accessible names. This is the most resilient
strategy because it mirrors how users and assistive technology perceive the page.

```python
# Signature
page.get_by_role(
    role: str,                        # ARIA role: "button", "link", "heading", "textbox", "checkbox", etc.
    *,
    name: str | re.Pattern = None,    # Accessible name (label text, aria-label, etc.)
    checked: bool = None,             # Filter by checked state
    disabled: bool = None,            # Filter by disabled state
    expanded: bool = None,            # Filter by expanded state (aria-expanded)
    include_hidden: bool = None,      # Include hidden elements
    level: int = None,                # Heading level (1-6)
    pressed: bool = None,             # Filter by pressed state (toggle buttons)
    selected: bool = None,            # Filter by selected state
    exact: bool = None,               # Exact name match (default is substring)
)
```

```python
# Examples
await page.get_by_role("button", name="Sign in").click()
await page.get_by_role("heading", name="Welcome", level=1)
await page.get_by_role("checkbox", name="Subscribe").check()
await page.get_by_role("link", name="Learn more").click()
await page.get_by_role("textbox", name="Search").fill("query")
await page.get_by_role("button", name=re.compile("submit", re.IGNORECASE)).click()

# Common ARIA roles:
# "alert", "banner", "button", "cell", "checkbox", "columnheader", "combobox",
# "complementary", "contentinfo", "definition", "dialog", "directory", "document",
# "feed", "figure", "form", "grid", "gridcell", "group", "heading", "img",
# "link", "list", "listbox", "listitem", "log", "main", "marquee", "math",
# "menu", "menubar", "menuitem", "menuitemcheckbox", "menuitemradio", "meter",
# "navigation", "none", "note", "option", "paragraph", "presentation",
# "progressbar", "radio", "radiogroup", "region", "row", "rowgroup",
# "rowheader", "scrollbar", "search", "searchbox", "separator", "slider",
# "spinbutton", "status", "strong", "switch", "tab", "table", "tablist",
# "tabpanel", "term", "textbox", "timer", "toolbar", "tooltip", "tree",
# "treegrid", "treeitem"
```

### 1.2 Text-Based Locators

```python
# get_by_text — matches elements containing the given text
page.get_by_text(
    text: str | re.Pattern,
    *,
    exact: bool = None,   # True = exact match; False (default) = substring, case-insensitive
)

await page.get_by_text("Welcome, John").click()
await page.get_by_text("Welcome, John", exact=True).click()
await page.get_by_text(re.compile("welcome", re.IGNORECASE)).click()
```

### 1.3 Label-Based Locators

```python
# get_by_label — finds input elements by associated <label> or aria-label
page.get_by_label(
    text: str | re.Pattern,
    *,
    exact: bool = None,
)

await page.get_by_label("Username").fill("john")
await page.get_by_label("Password").fill("secret")
```

### 1.4 Placeholder-Based Locators

```python
page.get_by_placeholder(
    text: str | re.Pattern,
    *,
    exact: bool = None,
)

await page.get_by_placeholder("name@example.com").fill("user@test.com")
```

### 1.5 Alt Text Locators

```python
page.get_by_alt_text(
    text: str | re.Pattern,
    *,
    exact: bool = None,
)

await page.get_by_alt_text("Company logo").click()
```

### 1.6 Title Locators

```python
page.get_by_title(
    text: str | re.Pattern,
    *,
    exact: bool = None,
)

await page.get_by_title("Issues count").text_content()
```

### 1.7 Test ID Locators

```python
page.get_by_test_id(test_id: str | re.Pattern)

await page.get_by_test_id("submit-button").click()

# Change the default test ID attribute (default is "data-testid")
playwright.selectors.set_test_id_attribute("data-pw")
```

### 1.8 CSS Selectors

```python
# Auto-detected (no prefix needed for CSS)
page.locator("button")
page.locator(".my-class")
page.locator("#my-id")
page.locator("div.container > button.primary")
page.locator("[data-action='submit']")

# Explicit prefix
page.locator("css=button.primary")

# Pseudo-classes for text matching
page.locator("article:has-text('Playwright')")          # Contains text (case-insensitive)
page.locator("#nav-bar :text('Home')")                   # Smallest element with text
page.locator("#nav-bar :text-is('Home')")                # Exact text (case-sensitive)
page.locator(":text-matches('Log\\s*in', 'i')")         # Regex text match

# Visibility filtering
page.locator("button:visible")

# Elements containing other elements
page.locator("article:has(div.promo)")

# Union of selectors (OR)
page.locator('button:has-text("Log in"), button:has-text("Sign in")')
```

### 1.9 XPath Selectors

```python
# Auto-detected when starting with // or ..
page.locator("//button")
page.locator("//div[@class='container']//a")

# Explicit prefix
page.locator("xpath=//button[@type='submit']")

# XPath union
page.locator("//span[contains(@class, 'spinner')]|//div[@id='confirmation']")

# Parent via XPath
page.locator("//button").locator("xpath=..")
```

### 1.10 Layout-Based Selectors

Useful when elements lack good semantic markup. Finds elements based on spatial position
relative to another element.

```python
# Right of an element
await page.locator("input:right-of(:text('Username'))").fill("value")

# Left of an element
await page.locator("[type=radio]:left-of(:text('Label 3'))").first.click()

# Below an element
await page.locator("button:below(:text('Username'))").click()

# Above an element
await page.locator("button:above(:text('Password'))").click()

# Near an element (within 50px default)
await page.locator("button:near(.promo-card)").click()

# Near with custom distance (120px)
await page.locator("button:near(:text('Username'), 120)").click()
```

### 1.11 ID and Data Attribute Selectors

```python
page.locator("id=username")
page.locator("data-testid=submit")
page.locator("data-test-id=submit")
page.locator("data-test=submit")
```

### 1.12 React and Vue Component Selectors

```python
# React components (requires React DevTools)
page.locator("_react=BookItem")
page.locator("_react=BookItem[author = 'Steven King']")
page.locator("_react=[author *= 'King']")        # substring
page.locator("_react=BookItem[author ^= 'St']")  # prefix
page.locator("_react=BookItem[author $= 'ng']")  # suffix
page.locator("_react=[author = /Steven(\\s+King)?/i]")  # regex

# Vue components (requires Vue DevTools)
page.locator("_vue=book-item")
page.locator("_vue=book-item[author = 'Steven King']")
```

### 1.13 Chaining and Filtering Locators

```python
# Chain: narrow down within a locator
product = page.get_by_role("listitem").filter(has_text="Product 2")
await product.get_by_role("button", name="Add to cart").click()

# filter() — narrow by text, child, or visibility
locator.filter(
    has_text: str | re.Pattern = None,       # Must contain text
    has_not_text: str | re.Pattern = None,   # Must NOT contain text
    has: Locator = None,                      # Must contain a child matching this locator
    has_not: Locator = None,                  # Must NOT contain a child matching this locator
    visible: bool = None,                     # Must be visible (True) or hidden (False)
)

# Filter by child element
await page.get_by_role("listitem").filter(
    has=page.get_by_role("heading", name="Product 2")
).get_by_role("button", name="Add to cart").click()

# Filter by NOT having text
await page.get_by_role("listitem").filter(has_not_text="Out of stock")

# Filter visible only
await page.locator("button").filter(visible=True).click()

# AND operator — both conditions must match
button = page.get_by_role("button").and_(page.get_by_title("Subscribe"))

# OR operator — either condition matches
new_email = page.get_by_role("button", name="New")
dialog = page.get_by_text("Confirm security settings")
await new_email.or_(dialog).first.click()

# Chaining selectors with >> operator
page.locator("article >> .bar >> span[attr=value]")
```

### 1.14 Nth Element, First, Last

```python
# By index (0-based)
page.locator("button").nth(0)    # first
page.locator("button").nth(-1)   # last

# Properties
page.locator("button").first
page.locator("button").last

# Nth-match pseudo-class
page.locator(":nth-match(:text('Buy'), 3)")

# Using locator("nth=N")
page.locator("button").locator("nth=0")
page.locator("button").locator("nth=-1")
```

### 1.15 Iterating Over All Matches

```python
# Get all matching locators as a list
all_items = await page.get_by_role("listitem").all()
for item in all_items:
    print(await item.text_content())

# Count elements
count = await page.get_by_role("listitem").count()

# Iterate by index
for i in range(await rows.count()):
    print(await rows.nth(i).text_content())

# Extract all text via JS (faster for large lists)
texts = await page.get_by_role("listitem").evaluate_all(
    "list => list.map(el => el.textContent)"
)
```

---

## 2. Element Inspection

### 2.1 Bounding Box

Returns the element's position and size relative to the viewport. Returns `None` if the
element is not visible.

```python
box = await locator.bounding_box(timeout=30000)
# Returns: {"x": float, "y": float, "width": float, "height": float} | None

if box:
    center_x = box["x"] + box["width"] / 2
    center_y = box["y"] + box["height"] / 2
```

### 2.2 Text Content

```python
# text_content() — returns the raw text content of the element (including hidden text)
text = await locator.text_content(timeout=30000)
# Returns: str | None

# inner_text() — returns the rendered text (respects CSS visibility)
text = await locator.inner_text(timeout=30000)
# Returns: str

# inner_html() — returns the inner HTML markup
html = await locator.inner_html(timeout=30000)
# Returns: str

# All texts from multiple matches
all_texts = await locator.all_text_contents()
# Returns: list[str]  (does NOT auto-wait)

all_inner = await locator.all_inner_texts()
# Returns: list[str]  (does NOT auto-wait)

# Input value
value = await locator.input_value(timeout=30000)
# Returns: str
```

### 2.3 Attributes

```python
href = await locator.get_attribute("href", timeout=30000)
# Returns: str | None

src = await locator.get_attribute("src")
data_id = await locator.get_attribute("data-id")
aria_label = await locator.get_attribute("aria-label")
```

### 2.4 Count

```python
count = await page.locator("button").count()
# Returns: int  (does NOT auto-wait)
```

### 2.5 State Checks

All state checks auto-wait for the element.

```python
visible = await locator.is_visible(timeout=30000)       # bool
hidden = await locator.is_hidden(timeout=30000)          # bool
enabled = await locator.is_enabled(timeout=30000)        # bool
disabled = await locator.is_disabled(timeout=30000)      # bool
editable = await locator.is_editable(timeout=30000)      # bool
checked = await locator.is_checked(timeout=30000)        # bool
```

### 2.6 JavaScript Evaluation

```python
# evaluate() — run JS in the context of the matched element
# The element is available as the first argument to the expression
result = await locator.evaluate("element => element.className")
result = await locator.evaluate("element => element.getBoundingClientRect()")
result = await locator.evaluate("(element, arg) => element.getAttribute(arg)", "href")

# evaluate_all() — run JS over ALL matched elements (no auto-wait)
texts = await locator.evaluate_all("elements => elements.map(e => e.textContent)")
hrefs = await locator.evaluate_all("elements => elements.map(e => e.href)")

# evaluate_handle() — returns a JSHandle instead of a serialized value
handle = await locator.evaluate_handle("element => element")
```

### 2.7 Page-Level JavaScript Evaluation

```python
# page.evaluate() — run arbitrary JS in the page context
title = await page.evaluate("document.title")
url = await page.evaluate("window.location.href")
scroll_y = await page.evaluate("window.scrollY")
height = await page.evaluate("document.body.scrollHeight")

# With arguments
result = await page.evaluate("selector => document.querySelector(selector).textContent", "#heading")

# Return complex objects
links = await page.evaluate("""
    () => Array.from(document.querySelectorAll('a')).map(a => ({
        href: a.href,
        text: a.textContent.trim(),
        visible: a.offsetParent !== null
    }))
""")
```

### 2.8 ARIA Snapshot (on Locator)

Modern replacement for the deprecated `page.accessibility.snapshot()`. Returns a YAML string
representing the accessibility tree within the locator's scope.

```python
snapshot = await page.locator("body").aria_snapshot(timeout=30000)
print(snapshot)
# Output example (YAML format):
# - banner:
#   - heading "My Website" [level=1]
#   - navigation "Main":
#     - list:
#       - listitem:
#         - link "Home"
#       - listitem:
#         - link "About"
# - main:
#   - heading "Welcome" [level=2]
#   - paragraph: "Some text here"
#   - button "Sign Up"
# - contentinfo:
#   - text "Copyright 2024"

# Scoped to a specific section
nav_snapshot = await page.locator("nav").aria_snapshot()
```

### 2.9 Highlight

Visually highlights the element on the page (useful for debugging).

```python
await locator.highlight()
```

### 2.10 Screenshot of Element

```python
# Screenshot a specific element
bytes_data = await locator.screenshot(
    path="element.png",           # Optional file path
    type="png",                   # "png" or "jpeg"
    quality=80,                   # JPEG quality (0-100)
    omit_background=False,        # Transparent background for PNG
    timeout=30000,
)
```

---

## 3. Accessibility Tree

### 3.1 page.accessibility.snapshot() (DEPRECATED)

**Status: Deprecated.** Use `locator.aria_snapshot()` (Section 2.8) instead.
Playwright recommends libraries like Axe for full accessibility testing.

Still functional but may be removed in future versions.

```python
snapshot = await page.accessibility.snapshot(
    interesting_only=True,   # Default: True. Prunes uninteresting nodes.
    root=None,               # Optional: an ElementHandle to snapshot from
)
```

**Return value:** A dictionary (or None) with this recursive structure:

```python
{
    "role": str,               # ARIA role ("button", "link", "heading", etc.)
    "name": str,               # Accessible name (visible text, aria-label, etc.)
    "value": str | float,      # Current value (for inputs, sliders, etc.)
    "description": str,        # Additional description (aria-describedby, etc.)
    "children": [              # Nested child nodes (same structure)
        { "role": ..., "name": ..., "children": [...] },
        ...
    ],
    # Optional boolean/state properties (present only when True or relevant):
    "checked": bool,           # Checkbox/radio state
    "disabled": bool,
    "expanded": bool,
    "focused": bool,
    "haspopup": str,
    "invalid": str,
    "level": int,              # Heading level (1-6)
    "modal": bool,
    "multiline": bool,
    "multiselectable": bool,
    "pressed": bool,           # Toggle button state
    "readonly": bool,
    "required": bool,
    "selected": bool,
    "autocomplete": str,
    "keyshortcuts": str,
    "orientation": str,
    "roledescription": str,
    "valuemax": float,
    "valuemin": float,
    "valuetext": str,
}
```

**Example: find a specific node by role**

```python
snapshot = await page.accessibility.snapshot()

def find_by_role(node, role):
    """Recursively find all nodes with a given role."""
    results = []
    if node.get("role") == role:
        results.append(node)
    for child in node.get("children", []):
        results.extend(find_by_role(child, role))
    return results

buttons = find_by_role(snapshot, "button")
links = find_by_role(snapshot, "link")

for btn in buttons:
    print(f"Button: {btn['name']}")
for link in links:
    print(f"Link: {link['name']}")
```

**Example: find the focused node**

```python
def find_focused(node):
    if node.get("focused"):
        return node
    for child in node.get("children", []):
        found = find_focused(child)
        if found:
            return found
    return None

snapshot = await page.accessibility.snapshot()
focused = find_focused(snapshot)
if focused:
    print(f"Focused: {focused['role']} - {focused['name']}")
```

**Example: get full tree with all nodes (including "uninteresting" ones)**

```python
snapshot = await page.accessibility.snapshot(interesting_only=False)
```

### 3.2 locator.aria_snapshot() (Modern Alternative)

Returns a YAML string. See Section 2.8 for details.

**Key differences from the deprecated method:**
- Returns YAML string (not dict)
- Scoped to a locator (not the whole page)
- Includes auto-waiting
- Not deprecated

---

## 4. Page Interaction

### 4.1 Click

```python
await locator.click(
    button="left",             # "left", "right", "middle"
    click_count=1,             # Number of clicks (2 for double-click)
    delay=0,                   # ms between mousedown and mouseup
    force=False,               # Skip actionability checks (visibility, etc.)
    modifiers=None,            # ["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]
    no_wait_after=False,       # Do not wait for navigation after click
    position=None,             # {"x": float, "y": float} — click at offset from top-left
    timeout=30000,
    trial=False,               # Perform actionability checks without clicking
)

# Common patterns
await locator.click()                                      # Simple click
await locator.click(button="right")                        # Right-click
await locator.click(click_count=2)                         # Double-click
await locator.click(modifiers=["Shift"])                   # Shift+click
await locator.click(modifiers=["ControlOrMeta"])           # Ctrl/Cmd+click (cross-platform)
await locator.click(position={"x": 0, "y": 0})            # Click top-left corner
await locator.click(force=True)                            # Skip actionability checks

# Double-click shorthand
await locator.dblclick()
```

### 4.2 Fill (Text Input)

```python
await locator.fill(
    value: str,
    force=False,
    no_wait_after=False,
    timeout=30000,
)

await page.get_by_role("textbox").fill("Hello World")
await page.get_by_label("Email").fill("user@example.com")
await page.get_by_label("Birth date").fill("2020-02-02")   # date inputs

# Clear a field
await locator.clear()
```

### 4.3 Type / Press Sequentially

Unlike `fill()`, this sends individual key events (useful for triggering autocomplete, etc.).

```python
await locator.press_sequentially(
    text: str,
    delay=0,              # ms between key presses
    no_wait_after=False,
    timeout=30000,
)

await page.locator("#search").press_sequentially("Hello World!", delay=100)
```

### 4.4 Keyboard

```python
# Press a single key or key combination
await locator.press("Enter")
await locator.press("Control+a")
await locator.press("Control+c")
await locator.press("Tab")
await locator.press("ArrowDown")

# Page-level keyboard (no element focus needed)
await page.keyboard.press("Escape")
await page.keyboard.press("PageDown")
await page.keyboard.press("Control+Shift+T")

# Type text character by character
await page.keyboard.type("Hello World!", delay=50)

# Insert text (emits only 'input' event, no keydown/keyup)
await page.keyboard.insert_text("Hello")

# Hold modifier keys
await page.keyboard.down("Shift")
await page.keyboard.press("ArrowLeft")
await page.keyboard.press("ArrowLeft")
await page.keyboard.up("Shift")
```

**Key names:** `F1`-`F12`, `Digit0`-`Digit9`, `KeyA`-`KeyZ`, `Backspace`, `Tab`, `Enter`,
`Escape`, `Space`, `ArrowLeft`, `ArrowRight`, `ArrowUp`, `ArrowDown`, `Home`, `End`,
`PageUp`, `PageDown`, `Delete`, `Insert`, `Shift`, `Control`, `Alt`, `Meta`, `ControlOrMeta`

### 4.5 Hover

```python
await locator.hover(
    force=False,
    modifiers=None,
    position=None,
    timeout=30000,
    trial=False,
)

await page.get_by_role("link", name="Products").hover()
```

### 4.6 Select Options (Dropdowns)

```python
# By value attribute
await locator.select_option("blue")
await locator.select_option(["red", "green", "blue"])

# By visible label
await locator.select_option(label="Blue")

# By index
await locator.select_option(index=2)

# By value object
await locator.select_option({"value": "blue"})
await locator.select_option({"label": "Blue"})
```

### 4.7 Checkboxes and Radio Buttons

```python
await locator.check()
await locator.uncheck()
await locator.set_checked(True)
await locator.set_checked(False)

is_checked = await locator.is_checked()
```

### 4.8 Focus and Blur

```python
await locator.focus()
await locator.blur()
```

### 4.9 Scrolling

```python
# Scroll element into view
await locator.scroll_into_view_if_needed(timeout=30000)

# Mouse wheel scrolling (hover first to target a scrollable area)
await page.locator("#scrollable-div").hover()
await page.mouse.wheel(0, 300)      # Scroll down 300px
await page.mouse.wheel(0, -300)     # Scroll up 300px
await page.mouse.wheel(300, 0)      # Scroll right 300px

# Keyboard scrolling
await page.keyboard.press("PageDown")
await page.keyboard.press("PageUp")
await page.keyboard.press("Home")
await page.keyboard.press("End")
await page.keyboard.press("ArrowDown")

# JavaScript scrolling
await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
await page.evaluate("window.scrollBy(0, 500)")
await page.evaluate("window.scrollTo(0, 0)")  # Scroll to top

# Scroll a specific container via JS
await page.locator("#container").evaluate("el => el.scrollTop += 100")
await page.locator("#container").evaluate("el => el.scrollTop = el.scrollHeight")
```

### 4.10 Mouse Operations (Low-Level)

```python
# Click at coordinates
await page.mouse.click(x=100, y=200, button="left", click_count=1, delay=0)

# Double-click at coordinates
await page.mouse.dblclick(x=100, y=200, button="left", delay=0)

# Move the mouse
await page.mouse.move(x=100, y=200, steps=1)  # steps = interpolation points

# Mouse button down/up
await page.mouse.down(button="left", click_count=1)
await page.mouse.up(button="left", click_count=1)

# Mouse wheel
await page.mouse.wheel(delta_x=0, delta_y=300)

# Drag and drop (manual)
await page.locator("#source").hover()
await page.mouse.down()
await page.locator("#target").hover()
await page.mouse.up()

# Drag and drop (high-level)
await page.locator("#source").drag_to(page.locator("#target"))
```

### 4.11 Dispatch Events

```python
# Dispatch a synthetic DOM event
await locator.dispatch_event("click")
await locator.dispatch_event("input", {"bubbles": True})
```

### 4.12 File Upload

```python
await page.get_by_label("Upload file").set_input_files("myfile.pdf")
await page.get_by_label("Upload files").set_input_files(["file1.txt", "file2.txt"])
await page.get_by_label("Upload file").set_input_files([])  # Clear

# Non-input file upload (via file chooser)
async with page.expect_file_chooser() as fc_info:
    await page.get_by_label("Upload").click()
file_chooser = await fc_info.value
await file_chooser.set_files("myfile.pdf")
```

---

## 5. Navigation and Waiting

### 5.1 page.goto()

```python
response = await page.goto(
    url: str,
    referer: str = None,        # Referer header
    timeout: float = 30000,     # ms, 0 to disable
    wait_until: str = "load",   # "load", "domcontentloaded", "networkidle", "commit"
)
# Returns: Response | None

await page.goto("https://example.com")
await page.goto("https://example.com", wait_until="networkidle")
await page.goto("https://example.com", wait_until="domcontentloaded")
```

**Wait-until states:**
- `"commit"` — response headers received (fastest)
- `"domcontentloaded"` — HTML parsed, DOMContentLoaded fired
- `"load"` — all resources loaded (default)
- `"networkidle"` — no network connections for 500ms (slowest, most reliable)

### 5.2 page.reload()

```python
response = await page.reload(
    timeout: float = 30000,
    wait_until: str = "load",
)
```

### 5.3 page.wait_for_load_state()

Wait for the page to reach a specific load state.

```python
await page.wait_for_load_state(
    state: str = "load",    # "load", "domcontentloaded", "networkidle"
    timeout: float = 30000,
)

# Common pattern: click then wait
await page.get_by_role("link", name="Dashboard").click()
await page.wait_for_load_state("networkidle")
```

### 5.4 page.wait_for_url()

Wait until the page URL matches a pattern.

```python
await page.wait_for_url(
    url: str | re.Pattern | Callable,   # glob, regex, or predicate function
    timeout: float = 30000,
    wait_until: str = "load",
)

await page.wait_for_url("**/dashboard")
await page.wait_for_url(re.compile(r"/login$"))
await page.wait_for_url(lambda url: "success" in url)
```

### 5.5 page.wait_for_selector() (Legacy)

Prefer `locator.wait_for()` instead. This is an older API but still functional.

```python
element = await page.wait_for_selector(
    selector: str,
    state: str = "visible",     # "attached", "detached", "visible", "hidden"
    strict: bool = False,
    timeout: float = 30000,
)

await page.wait_for_selector("div.products", state="visible")
await page.wait_for_selector("#loading-spinner", state="detached")
await page.wait_for_selector("iframe[src*='widget']", state="attached")
```

### 5.6 locator.wait_for() (Preferred)

```python
await locator.wait_for(
    state: str = "visible",    # "attached", "detached", "visible", "hidden"
    timeout: float = 30000,
)

# Wait for element to appear
await page.locator("#results").wait_for(state="visible")

# Wait for loading indicator to disappear
await page.locator(".spinner").wait_for(state="detached")

# Wait for element to exist in DOM (even if hidden)
await page.locator("#lazy-content").wait_for(state="attached")
```

**States:**
- `"attached"` — element exists in DOM (may be invisible)
- `"detached"` — element removed from DOM
- `"visible"` — element visible (non-empty bounding box, no `visibility: hidden`)
- `"hidden"` — element hidden or not in DOM

### 5.7 page.wait_for_function()

Wait for a JavaScript function to return a truthy value.

```python
await page.wait_for_function(
    expression: str,
    arg: Any = None,
    polling: float | str = "raf",   # polling interval ms, or "raf" for requestAnimationFrame
    timeout: float = 30000,
)

# Wait for a JS condition
await page.wait_for_function("document.querySelector('#app').dataset.loaded === 'true'")
await page.wait_for_function("window.appReady === true")
await page.wait_for_function("() => document.querySelectorAll('.item').length > 10")
```

### 5.8 page.wait_for_event()

```python
# Wait for a specific event
async with page.expect_event("popup") as popup_info:
    await page.get_by_role("link", name="Open").click()
popup = await popup_info.value

# Wait for console message
async with page.expect_event("console", lambda msg: "error" in msg.text.lower()):
    await page.reload()
```

### 5.9 page.wait_for_timeout()

Simple delay. Use sparingly (prefer auto-waiting).

```python
await page.wait_for_timeout(1000)  # Wait 1 second
```

### 5.10 page.wait_for_response() / page.wait_for_request()

```python
# Wait for an API response
async with page.expect_response("**/api/data") as response_info:
    await page.get_by_role("button", name="Load").click()
response = await response_info.value
data = await response.json()

# Wait for a request
async with page.expect_request("**/api/data") as request_info:
    await page.get_by_role("button", name="Submit").click()
request = await request_info.value
```

### 5.11 Navigation Lifecycle

When `page.goto()` is called, the lifecycle events fire in this order:
1. Navigation starts (URL change)
2. Navigation commits (response headers parsed, `page.url` updated)
3. `domcontentloaded` fires (HTML parsed)
4. `load` fires (all resources loaded, images rendered)
5. `networkidle` (no network connections for 500ms)

---

## 6. Enumerating Clickable Elements

### 6.1 Get All Links

```python
# Using role locator (recommended)
links = page.get_by_role("link")
count = await links.count()
for i in range(count):
    link = links.nth(i)
    text = await link.text_content()
    href = await link.get_attribute("href")
    visible = await link.is_visible()
    print(f"Link: {text} -> {href} (visible: {visible})")

# Using .all() iterator
for link in await page.get_by_role("link").all():
    text = await link.text_content()
    href = await link.get_attribute("href")
    print(f"{text}: {href}")

# Bulk extraction via JS (fastest)
links = await page.evaluate("""
    () => Array.from(document.querySelectorAll('a')).map(a => ({
        href: a.href,
        text: a.textContent.trim(),
        visible: a.offsetParent !== null,
        rect: a.getBoundingClientRect().toJSON()
    }))
""")
```

### 6.2 Get All Buttons

```python
# Using role locator
buttons = page.get_by_role("button")
count = await buttons.count()
for i in range(count):
    btn = buttons.nth(i)
    text = await btn.text_content()
    enabled = await btn.is_enabled()
    visible = await btn.is_visible()
    print(f"Button: {text} (enabled: {enabled}, visible: {visible})")

# Via JS — includes button elements AND elements with role="button"
buttons = await page.evaluate("""
    () => {
        const selectors = 'button, [role="button"], input[type="submit"], input[type="button"]';
        return Array.from(document.querySelectorAll(selectors)).map(el => ({
            tag: el.tagName,
            text: el.textContent.trim() || el.value || el.getAttribute('aria-label') || '',
            type: el.type || '',
            disabled: el.disabled,
            visible: el.offsetParent !== null,
            rect: el.getBoundingClientRect().toJSON()
        }));
    }
""")
```

### 6.3 Get All Clickable Elements (Comprehensive)

```python
# Comprehensive JS query for all interactive elements
clickable = await page.evaluate("""
    () => {
        const interactive = document.querySelectorAll(`
            a[href],
            button,
            input[type="button"],
            input[type="submit"],
            input[type="reset"],
            [role="button"],
            [role="link"],
            [role="menuitem"],
            [role="tab"],
            [onclick],
            [tabindex]:not([tabindex="-1"]),
            details > summary
        `);
        return Array.from(interactive).map((el, index) => ({
            index: index,
            tag: el.tagName.toLowerCase(),
            role: el.getAttribute('role') || el.tagName.toLowerCase(),
            text: (el.textContent || '').trim().substring(0, 100),
            ariaLabel: el.getAttribute('aria-label') || '',
            href: el.href || '',
            type: el.type || '',
            id: el.id || '',
            className: el.className || '',
            disabled: el.disabled || false,
            visible: el.offsetParent !== null && el.getBoundingClientRect().height > 0,
            rect: el.getBoundingClientRect().toJSON()
        }));
    }
""")

# Filter to visible only
visible_clickable = [el for el in clickable if el["visible"]]
```

### 6.4 Get All Form Inputs

```python
inputs = await page.evaluate("""
    () => Array.from(document.querySelectorAll('input, textarea, select')).map(el => ({
        tag: el.tagName.toLowerCase(),
        type: el.type || '',
        name: el.name || '',
        id: el.id || '',
        placeholder: el.placeholder || '',
        value: el.value || '',
        label: el.labels?.[0]?.textContent?.trim() || el.getAttribute('aria-label') || '',
        required: el.required,
        disabled: el.disabled,
        visible: el.offsetParent !== null
    }))
""")
```

### 6.5 Get All Navigation Menu Items

```python
# Using the accessibility tree
nav_links = page.locator("nav").get_by_role("link")
for link in await nav_links.all():
    text = await link.text_content()
    href = await link.get_attribute("href")
    print(f"Nav: {text} -> {href}")

# Or scope to a specific nav
main_nav = page.locator("nav.main-navigation")
items = await main_nav.get_by_role("link").all()
```

### 6.6 Using the Accessibility Snapshot for Element Discovery

```python
# Get the full page accessibility tree (deprecated but still works)
snapshot = await page.accessibility.snapshot(interesting_only=False)

def collect_interactive(node, results=None):
    if results is None:
        results = []
    role = node.get("role", "")
    if role in ("button", "link", "menuitem", "tab", "checkbox", "radio",
                "textbox", "combobox", "searchbox", "switch", "slider"):
        results.append({
            "role": role,
            "name": node.get("name", ""),
            "value": node.get("value"),
            "disabled": node.get("disabled", False),
            "checked": node.get("checked"),
            "expanded": node.get("expanded"),
        })
    for child in node.get("children", []):
        collect_interactive(child, results)
    return results

interactive_elements = collect_interactive(snapshot)
for el in interactive_elements:
    print(f"[{el['role']}] {el['name']}")

# Modern alternative: locator.aria_snapshot()
yaml_tree = await page.locator("body").aria_snapshot()
print(yaml_tree)
```

---

## 7. Frames and Iframes

### 7.1 FrameLocator (Recommended)

```python
# Locate elements inside an iframe
username = page.frame_locator(".frame-class").get_by_label("User Name")
await username.fill("John")

# Via locator.content_frame
frame = page.locator("iframe[name='embedded']").content_frame
await frame.get_by_role("button", name="Submit").click()

# Nested iframes
nested = page.frame_locator("#outer-iframe").frame_locator("#inner-iframe")
await nested.get_by_role("button", name="OK").click()
```

### 7.2 FrameLocator Methods

All standard `get_by_*` methods are available on FrameLocator:

```python
frame = page.frame_locator("#my-iframe")

frame.get_by_role("button", name="Submit")
frame.get_by_text("Hello")
frame.get_by_label("Email")
frame.get_by_placeholder("Enter name")
frame.get_by_alt_text("Logo")
frame.get_by_title("Tooltip")
frame.get_by_test_id("my-element")
frame.locator("css=div.container")
frame.frame_locator("#nested-iframe")  # Nested iframe access
```

### 7.3 Frame Object (Legacy but Useful)

```python
# Get frame by name attribute
frame = page.frame("frame-login")

# Get frame by URL pattern
frame = page.frame(url=re.compile(r".*domain.*"))

# Interact directly with frame
await frame.fill("#username", "John")
await frame.click("#submit")

# List all frames
for f in page.frames:
    print(f.url)
```

### 7.4 FrameLocator.owner

Convert a FrameLocator back to a Locator pointing at the iframe element itself:

```python
frame = page.frame_locator("iframe[name='embedded']")
iframe_locator = frame.owner
box = await iframe_locator.bounding_box()  # Get iframe position/size
```

---

## 8. Practical Patterns for AI Agents

### 8.1 Discovering Page Structure

```python
async def discover_page(page):
    """Get a comprehensive view of the page for an AI agent."""

    # 1. Get page metadata
    title = await page.title()
    url = page.url

    # 2. Get accessibility tree (best for understanding structure)
    aria_yaml = await page.locator("body").aria_snapshot()

    # 3. Get all interactive elements with positions
    interactive = await page.evaluate("""
        () => {
            const elements = document.querySelectorAll(`
                a[href], button, [role="button"], [role="link"],
                input, textarea, select, [role="menuitem"], [role="tab"],
                [onclick], [tabindex]:not([tabindex="-1"])
            `);
            return Array.from(elements)
                .filter(el => el.offsetParent !== null)
                .map((el, i) => ({
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || '',
                    text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().substring(0, 80),
                    href: el.href || '',
                    rect: el.getBoundingClientRect().toJSON()
                }));
        }
    """)

    return {
        "title": title,
        "url": url,
        "aria_tree": aria_yaml,
        "interactive_elements": interactive,
    }
```

### 8.2 Reliable Click by Text (with Fallbacks)

```python
async def click_element(page, description: str):
    """Try multiple strategies to click an element described by text."""

    # Strategy 1: Role-based (most reliable)
    for role in ["button", "link", "menuitem", "tab"]:
        locator = page.get_by_role(role, name=description)
        if await locator.count() == 1:
            await locator.click()
            return True

    # Strategy 2: Exact text match
    locator = page.get_by_text(description, exact=True)
    if await locator.count() == 1:
        await locator.click()
        return True

    # Strategy 3: Substring text match
    locator = page.get_by_text(description)
    if await locator.count() == 1:
        await locator.click()
        return True

    # Strategy 4: Case-insensitive regex
    locator = page.get_by_text(re.compile(re.escape(description), re.IGNORECASE))
    if await locator.count() >= 1:
        await locator.first.click()
        return True

    # Strategy 5: CSS selector fallback
    locator = page.locator(f":text-is('{description}')")
    if await locator.count() >= 1:
        await locator.first.click()
        return True

    return False
```

### 8.3 Wait for Page to Be Fully Loaded

```python
async def wait_for_page_ready(page, timeout=30000):
    """Wait for page to be fully loaded and interactive."""
    await page.wait_for_load_state("networkidle", timeout=timeout)
    # Additional check: wait for no loading indicators
    try:
        await page.locator(".loading, .spinner, [aria-busy='true']").wait_for(
            state="detached", timeout=5000
        )
    except:
        pass  # No loading indicators found, that's fine
```

### 8.4 Safe Navigation with Error Handling

```python
async def safe_goto(page, url, timeout=30000):
    """Navigate to URL with robust error handling."""
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        # Wait a bit more for dynamic content
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except:
            pass  # networkidle timeout is OK, page may have persistent connections
        return response
    except Exception as e:
        print(f"Navigation error: {e}")
        return None
```

### 8.5 Scroll Through Entire Page

```python
async def scroll_full_page(page, step=500, delay=200):
    """Scroll through the entire page to trigger lazy loading."""
    total_height = await page.evaluate("document.body.scrollHeight")
    current = 0
    while current < total_height:
        await page.evaluate(f"window.scrollTo(0, {current})")
        await page.wait_for_timeout(delay)
        current += step
        # Re-check height (may grow with lazy loading)
        total_height = await page.evaluate("document.body.scrollHeight")
    # Scroll back to top
    await page.evaluate("window.scrollTo(0, 0)")
```

### 8.6 Take Screenshot with Element Annotations

```python
async def screenshot_with_annotations(page, path="screenshot.png"):
    """Take a screenshot and return element positions for AI vision models."""
    # Get all interactive elements with bounding boxes
    elements = await page.evaluate("""
        () => {
            const els = document.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"]');
            return Array.from(els)
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && el.offsetParent !== null;
                })
                .map((el, i) => ({
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().substring(0, 50),
                    rect: el.getBoundingClientRect().toJSON()
                }));
        }
    """)

    screenshot_bytes = await page.screenshot(path=path, type="jpeg", quality=80)
    return {"screenshot": screenshot_bytes, "elements": elements}
```

### 8.7 Get Visible Text Content of Page

```python
async def get_page_text(page):
    """Get all visible text content from the page."""
    return await page.evaluate("""
        () => {
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: (node) => {
                        const el = node.parentElement;
                        if (!el) return NodeFilter.FILTER_REJECT;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') {
                            return NodeFilter.FILTER_REJECT;
                        }
                        return node.textContent.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                    }
                }
            );
            const texts = [];
            while (walker.nextNode()) {
                texts.push(walker.currentNode.textContent.trim());
            }
            return texts.join('\\n');
        }
    """)
```

---

## Quick Reference Table

| Task | Best Method |
|---|---|
| Find button by label | `page.get_by_role("button", name="Submit")` |
| Find link by text | `page.get_by_role("link", name="Learn more")` |
| Find input by label | `page.get_by_label("Email")` |
| Find by placeholder | `page.get_by_placeholder("Enter email")` |
| Find by CSS class | `page.locator(".my-class")` |
| Find by ID | `page.locator("#my-id")` |
| Find by XPath | `page.locator("//div[@class='container']")` |
| Find inside iframe | `page.frame_locator("#iframe").get_by_role(...)` |
| Find near another element | `page.locator("input:right-of(:text('Label'))")` |
| Get element position | `await locator.bounding_box()` |
| Get element text | `await locator.text_content()` |
| Check visibility | `await locator.is_visible()` |
| Count matches | `await locator.count()` |
| Get all matching | `await locator.all()` |
| Wait for element | `await locator.wait_for(state="visible")` |
| Wait for navigation | `await page.wait_for_url("**/dashboard")` |
| Wait for network idle | `await page.wait_for_load_state("networkidle")` |
| Run JavaScript | `await page.evaluate("expression")` |
| Get accessibility tree | `await page.locator("body").aria_snapshot()` |
| Scroll into view | `await locator.scroll_into_view_if_needed()` |
| Scroll page | `await page.mouse.wheel(0, 300)` |
| Click at coordinates | `await page.mouse.click(100, 200)` |
