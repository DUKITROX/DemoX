/**
 * DemoX Content Script — captures instructor browsing events.
 *
 * Only active when the current page origin matches the demo base URL.
 * Sends events to the background service worker via chrome.runtime.sendMessage.
 */

(() => {
  "use strict";

  let active = false;
  let roomId = null;
  let baseOrigin = null;

  // ── Helpers ──────────────────────────────────────────────────────────

  function getElementInfo(el) {
    if (!el || !el.tagName) return null;
    const tag = el.tagName.toLowerCase();
    const text = (el.textContent || "").trim().slice(0, 120);
    const role = el.getAttribute("role") || el.closest("[role]")?.getAttribute("role") || "";
    const ariaLabel = el.getAttribute("aria-label") || "";
    const href = el.getAttribute("href") || "";

    // Determine if element is inside a nav region
    const inNav = !!(
      el.closest("nav") ||
      el.closest("[role='navigation']") ||
      el.closest("header")
    );

    return { tag, text, role, aria_label: ariaLabel, href, in_nav: inNav };
  }

  function getFieldLabel(el) {
    // Try: associated label, placeholder, aria-label, name
    if (el.id) {
      const label = document.querySelector(`label[for="${el.id}"]`);
      if (label) return label.textContent.trim();
    }
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) return ariaLabel;
    const placeholder = el.getAttribute("placeholder");
    if (placeholder) return placeholder;
    return el.getAttribute("name") || el.tagName.toLowerCase();
  }

  function sendEvent(type, data) {
    if (!active || !roomId) return;
    const event = { type, timestamp: Date.now() / 1000, url: location.href, ...data };
    console.log(`[DemoX] ${type}:`, event);
    chrome.runtime.sendMessage({ action: "demox_event", roomId, event });
  }

  // ── Event Handlers ──────────────────────────────────────────────────

  // Navigation: SPA detection via history monkey-patch + popstate
  function setupNavigationCapture() {
    // Initial page load
    sendEvent("navigation", { url: location.href, title: document.title });

    // Monkey-patch pushState / replaceState for SPA navigation
    const origPush = history.pushState;
    const origReplace = history.replaceState;

    history.pushState = function (...args) {
      origPush.apply(this, args);
      setTimeout(() => {
        sendEvent("navigation", { url: location.href, title: document.title });
      }, 50);
    };

    history.replaceState = function (...args) {
      origReplace.apply(this, args);
      setTimeout(() => {
        sendEvent("navigation", { url: location.href, title: document.title });
      }, 50);
    };

    window.addEventListener("popstate", () => {
      setTimeout(() => {
        sendEvent("navigation", { url: location.href, title: document.title });
      }, 50);
    });
  }

  // Click capture
  function setupClickCapture() {
    document.addEventListener("click", (e) => {
      const el = e.target.closest("a, button, [role='button'], [role='link'], [role='menuitem'], [role='tab'], input[type='submit']");
      const info = getElementInfo(el || e.target);
      if (!info) return;
      sendEvent("click", {
        target_text: info.text,
        tag: info.tag,
        role: info.role,
        aria_label: info.aria_label,
        href: info.href,
        position: { x: e.clientX, y: e.clientY },
        in_nav: info.in_nav,
      });
    }, true);
  }

  // Scroll capture (throttled 500ms, ignore <50px)
  function setupScrollCapture() {
    let lastScrollY = window.scrollY;
    let scrollTimer = null;

    window.addEventListener("scroll", () => {
      if (scrollTimer) return;
      scrollTimer = setTimeout(() => {
        scrollTimer = null;
        const currentY = window.scrollY;
        const deltaY = currentY - lastScrollY;
        if (Math.abs(deltaY) < 50) return;
        sendEvent("scroll", {
          scroll_y: currentY,
          delta_y: deltaY,
          direction: deltaY > 0 ? "down" : "up",
        });
        lastScrollY = currentY;
      }, 500);
    }, { passive: true });
  }

  // Input capture (debounced 1s)
  function setupInputCapture() {
    let inputTimers = new Map();

    document.addEventListener("input", (e) => {
      const el = e.target;
      if (!el.tagName) return;
      const tag = el.tagName.toLowerCase();
      if (tag !== "input" && tag !== "textarea" && tag !== "select") return;
      // Don't capture password fields
      if (el.type === "password") return;

      const key = el.id || el.name || el.getAttribute("aria-label") || "unknown";
      if (inputTimers.has(key)) clearTimeout(inputTimers.get(key));

      inputTimers.set(key, setTimeout(() => {
        inputTimers.delete(key);
        sendEvent("input", {
          field_label: getFieldLabel(el),
          field_type: el.type || tag,
          value: el.value.slice(0, 200),
        });
      }, 1000));
    }, true);
  }

  // ── Activation ──────────────────────────────────────────────────────

  function activate(config) {
    if (active) return;
    roomId = config.roomId;
    baseOrigin = config.baseOrigin;

    // Check if current page origin matches demo base URL
    if (location.origin !== baseOrigin) {
      console.log(`[DemoX] Origin mismatch: ${location.origin} !== ${baseOrigin}. Inactive.`);
      return;
    }

    active = true;
    console.log(`[DemoX] Activated for room ${roomId} on ${baseOrigin}`);

    setupNavigationCapture();
    setupClickCapture();
    setupScrollCapture();
    setupInputCapture();
  }

  function deactivate() {
    active = false;
    roomId = null;
    console.log("[DemoX] Deactivated");
  }

  // ── Message Listener (from background) ──────────────────────────────

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "demox_activate") {
      activate(msg);
    } else if (msg.action === "demox_deactivate") {
      deactivate();
    }
  });

  // On load, ask background if we should be active
  chrome.runtime.sendMessage({ action: "demox_content_ready", origin: location.origin });
})();
