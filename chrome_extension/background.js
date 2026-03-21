/**
 * DemoX Background Service Worker — manages room detection, event posting,
 * status polling, and mode switching.
 */

const BACKEND_BASE = "http://localhost:8000";
const STATUS_POLL_INTERVAL = 30_000; // 30 seconds

let state = {
  roomId: null,
  baseOrigin: null,
  baseUrl: null,
  currentMode: null,
  eventCount: 0,
  connected: false,
  eventBuffer: [],
  flushTimer: null,
};

let statusPollTimer = null;

// ── Event Buffering & Flush ──────────────────────────────────────────

function bufferEvent(roomId, event) {
  state.eventBuffer.push(event);
  state.eventCount++;

  // Flush every 2 seconds or when buffer hits 20 events
  if (!state.flushTimer) {
    state.flushTimer = setTimeout(() => flushEvents(roomId), 2000);
  }
  if (state.eventBuffer.length >= 20) {
    flushEvents(roomId);
  }
}

async function flushEvents(roomId) {
  if (state.flushTimer) {
    clearTimeout(state.flushTimer);
    state.flushTimer = null;
  }

  const events = state.eventBuffer.splice(0);
  if (events.length === 0) return;

  try {
    const resp = await fetch(`${BACKEND_BASE}/api/demo/${roomId}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
    });
    if (!resp.ok) {
      console.warn(`[DemoX Background] POST events failed: ${resp.status}`);
    } else {
      console.log(`[DemoX Background] Flushed ${events.length} events`);
    }
  } catch (err) {
    console.error(`[DemoX Background] POST events error:`, err);
    // Re-add events to buffer on failure
    state.eventBuffer.unshift(...events);
  }
}

// ── Status Polling ──────────────────────────────────────────────────

async function pollStatus() {
  if (!state.roomId) return;

  try {
    const resp = await fetch(`${BACKEND_BASE}/api/demo/${state.roomId}/status`);
    if (resp.status === 404) {
      console.log("[DemoX Background] Room not found, disconnecting");
      disconnect();
      return;
    }
    const data = await resp.json();
    if (data.status === "stopped") {
      console.log("[DemoX Background] Room stopped, disconnecting");
      disconnect();
      return;
    }
    // Update mode from status
    if (data.mode) {
      state.currentMode = data.mode;
    }
    console.log(`[DemoX Background] Status poll: ${data.status}, mode: ${data.mode || "unknown"}`);
  } catch (err) {
    console.error("[DemoX Background] Status poll error:", err);
  }
}

function startStatusPolling() {
  stopStatusPolling();
  pollStatus(); // immediate first poll
  statusPollTimer = setInterval(pollStatus, STATUS_POLL_INTERVAL);
}

function stopStatusPolling() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer);
    statusPollTimer = null;
  }
}

// ── Room Connection ──────────────────────────────────────────────────

async function connectToRoom(roomId) {
  console.log(`[DemoX Background] Connecting to room: ${roomId}`);

  try {
    const resp = await fetch(`${BACKEND_BASE}/api/demo/${roomId}/status`);
    if (!resp.ok) {
      console.warn(`[DemoX Background] Room status failed: ${resp.status}`);
      return false;
    }
    const data = await resp.json();

    state.roomId = roomId;
    state.baseUrl = data.url;
    state.baseOrigin = new URL(data.url).origin;
    state.currentMode = data.mode || "student";
    state.connected = true;
    state.eventCount = 0;
    state.eventBuffer = [];

    console.log(`[DemoX Background] Connected: room=${roomId}, url=${data.url}, origin=${state.baseOrigin}`);

    // Start polling
    startStatusPolling();

    // Notify all matching tabs
    notifyTabs();

    return true;
  } catch (err) {
    console.error("[DemoX Background] Connect error:", err);
    return false;
  }
}

function disconnect() {
  // Flush remaining events
  if (state.roomId && state.eventBuffer.length > 0) {
    flushEvents(state.roomId);
  }

  const wasConnected = state.connected;
  state.roomId = null;
  state.baseOrigin = null;
  state.baseUrl = null;
  state.currentMode = null;
  state.connected = false;
  state.eventCount = 0;
  state.eventBuffer = [];

  stopStatusPolling();

  if (wasConnected) {
    // Notify all tabs to deactivate
    chrome.tabs.query({}, (tabs) => {
      for (const tab of tabs) {
        chrome.tabs.sendMessage(tab.id, { action: "demox_deactivate" }).catch(() => {});
      }
    });
  }

  console.log("[DemoX Background] Disconnected");
}

// ── Tab Notification ────────────────────────────────────────────────

function notifyTabs() {
  if (!state.connected) return;
  chrome.tabs.query({}, (tabs) => {
    for (const tab of tabs) {
      if (tab.url && tab.url.startsWith(state.baseOrigin)) {
        chrome.tabs.sendMessage(tab.id, {
          action: "demox_activate",
          roomId: state.roomId,
          baseOrigin: state.baseOrigin,
        }).catch(() => {});
      }
    }
  });
}

// ── Mode Switch ─────────────────────────────────────────────────────

async function switchMode(targetMode) {
  if (!state.roomId) return { success: false, error: "Not connected" };

  try {
    const resp = await fetch(`${BACKEND_BASE}/api/demo/${state.roomId}/mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: targetMode }),
    });
    if (!resp.ok) {
      const text = await resp.text();
      console.warn(`[DemoX Background] Mode switch failed: ${resp.status} ${text}`);
      return { success: false, error: text };
    }
    const data = await resp.json();
    state.currentMode = targetMode;
    console.log(`[DemoX Background] Mode switched to: ${targetMode}`);
    return { success: true, mode: targetMode };
  } catch (err) {
    console.error("[DemoX Background] Mode switch error:", err);
    return { success: false, error: err.message };
  }
}

// ── Message Handlers ────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Content script ready — check if it should activate
  if (msg.action === "demox_content_ready") {
    if (state.connected && state.baseOrigin && msg.origin === state.baseOrigin) {
      chrome.tabs.sendMessage(sender.tab.id, {
        action: "demox_activate",
        roomId: state.roomId,
        baseOrigin: state.baseOrigin,
      }).catch(() => {});
    }
    return;
  }

  // Event from content script
  if (msg.action === "demox_event" && msg.roomId && msg.event) {
    bufferEvent(msg.roomId, msg.event);
    return;
  }

  // Popup requests
  if (msg.action === "demox_get_state") {
    sendResponse({
      roomId: state.roomId,
      baseUrl: state.baseUrl,
      currentMode: state.currentMode,
      eventCount: state.eventCount,
      connected: state.connected,
    });
    return true;
  }

  if (msg.action === "demox_connect") {
    connectToRoom(msg.roomId).then((ok) => {
      sendResponse({ success: ok });
    });
    return true; // async response
  }

  if (msg.action === "demox_disconnect") {
    disconnect();
    sendResponse({ success: true });
    return true;
  }

  if (msg.action === "demox_switch_mode") {
    switchMode(msg.mode).then((result) => {
      sendResponse(result);
    });
    return true;
  }
});

// ── Tab change detection ────────────────────────────────────────────

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!state.connected || !state.baseOrigin) return;
  if (changeInfo.status === "complete" && tab.url && tab.url.startsWith(state.baseOrigin)) {
    chrome.tabs.sendMessage(tabId, {
      action: "demox_activate",
      roomId: state.roomId,
      baseOrigin: state.baseOrigin,
    }).catch(() => {});
  }

  // Auto-detect room from DemoX frontend tab
  if (changeInfo.status === "complete" && tab.url && tab.url.includes("localhost:3000/demo/")) {
    const match = tab.url.match(/\/demo\/(demo-[a-f0-9]+)/);
    if (match && !state.connected) {
      console.log(`[DemoX Background] Auto-detected room from tab: ${match[1]}`);
      connectToRoom(match[1]);
    }
  }
});
