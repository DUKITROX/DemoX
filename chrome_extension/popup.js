/**
 * DemoX Extension Popup — connection status, event count, mode switch.
 */

const disconnectedDiv = document.getElementById("disconnected");
const connectedDiv = document.getElementById("connected");
const roomInput = document.getElementById("room-input");
const connectBtn = document.getElementById("connect-btn");
const disconnectBtn = document.getElementById("disconnect-btn");
const modeBtn = document.getElementById("mode-btn");
const eventCountEl = document.getElementById("event-count");
const modeDisplayEl = document.getElementById("mode-display");
const roomInfoEl = document.getElementById("room-info");
const urlInfoEl = document.getElementById("url-info");

let currentState = null;

function updateUI(s) {
  currentState = s;
  if (s && s.connected) {
    disconnectedDiv.classList.add("hidden");
    connectedDiv.classList.remove("hidden");
    roomInfoEl.textContent = `Room: ${s.roomId}`;
    urlInfoEl.textContent = `URL: ${s.baseUrl || "unknown"}`;
    eventCountEl.textContent = String(s.eventCount || 0);

    const mode = s.currentMode || "student";
    modeDisplayEl.textContent = mode;
    if (mode === "student") {
      modeBtn.textContent = "Switch to Demo Mode";
      modeBtn.className = "btn-mode";
    } else {
      modeBtn.textContent = "Switch to Student Mode";
      modeBtn.className = "btn-mode";
    }
  } else {
    disconnectedDiv.classList.remove("hidden");
    connectedDiv.classList.add("hidden");
  }
}

function refreshState() {
  chrome.runtime.sendMessage({ action: "demox_get_state" }, (resp) => {
    if (chrome.runtime.lastError) return;
    updateUI(resp);
  });
}

// Connect button
connectBtn.addEventListener("click", () => {
  const roomId = roomInput.value.trim();
  if (!roomId) return;
  connectBtn.textContent = "Connecting...";
  connectBtn.className = "btn-disabled";
  chrome.runtime.sendMessage({ action: "demox_connect", roomId }, (resp) => {
    if (resp && resp.success) {
      refreshState();
    } else {
      connectBtn.textContent = "Connect";
      connectBtn.className = "btn-primary";
      alert("Could not connect. Is the demo session active?");
    }
  });
});

// Disconnect button
disconnectBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ action: "demox_disconnect" }, () => {
    refreshState();
  });
});

// Mode switch button
modeBtn.addEventListener("click", () => {
  if (!currentState || !currentState.connected) return;
  const targetMode = currentState.currentMode === "student" ? "demo_expert" : "student";
  modeBtn.textContent = "Switching...";
  modeBtn.className = "btn-disabled";
  chrome.runtime.sendMessage({ action: "demox_switch_mode", mode: targetMode }, (resp) => {
    if (resp && resp.success) {
      refreshState();
    } else {
      refreshState();
      alert(`Mode switch failed: ${resp?.error || "unknown error"}`);
    }
  });
});

// Refresh every 2 seconds
refreshState();
setInterval(refreshState, 2000);
