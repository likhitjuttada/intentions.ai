// background.js — service worker
// Polls the active tab, captures screenshots, sends to backend for analysis.

const BACKEND_URL = "http://localhost:8080";
const POLL_INTERVAL_MS = 5000;   // base poll interval
const DEBOUNCE_MS = 3000;        // min gap between sends

let lastSentAt = 0;
let lastScreenshotHash = null;
let lastTabId = null;
let lastUrl = null;

// Simple hash for change detection (djb2 on first 2000 chars of base64)
function quickHash(str) {
  let hash = 5381;
  const sample = str.slice(0, 2000);
  for (let i = 0; i < sample.length; i++) {
    hash = ((hash << 5) + hash) + sample.charCodeAt(i);
    hash |= 0;
  }
  return hash;
}

async function getGeolocation(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => new Promise((resolve) => {
        if (!navigator.geolocation) { resolve(null); return; }
        navigator.geolocation.getCurrentPosition(
          (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
          () => resolve(null),
          { timeout: 3000 }
        );
      })
    });
    return results?.[0]?.result ?? null;
  } catch {
    return null;
  }
}

async function captureAndSend(tab) {
  const now = Date.now();
  if (now - lastSentAt < DEBOUNCE_MS) return;

  let dataUrl;
  try {
    dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
  } catch (e) {
    // Tab may not be capturable (e.g., chrome:// pages)
    return;
  }

  const hash = quickHash(dataUrl);
  const urlChanged = tab.url !== lastUrl;

  // Skip if screenshot looks identical and URL hasn't changed
  if (hash === lastScreenshotHash && !urlChanged) return;

  lastSentAt = now;
  lastScreenshotHash = hash;
  lastUrl = tab.url;

  const base64Image = dataUrl.split(",")[1]; // strip data:image/png;base64,
  const geolocation = await getGeolocation(tab.id);

  const payload = {
    screenshot: base64Image,
    url: tab.url,
    title: tab.title,
    geolocation
  };

  try {
    const response = await fetch(`${BACKEND_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      console.warn("Backend error:", response.status);
      return;
    }

    const data = await response.json();

    // Forward cards to content script
    if (data.cards && data.cards.length > 0) {
      chrome.tabs.sendMessage(tab.id, { type: "NEW_CARDS", cards: data.cards, url: tab.url })
        .catch(() => {}); // content script may not be ready
    }
  } catch (e) {
    console.error("Fetch error:", e);
  }
}

async function pollActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://")) return;

  if (tab.id !== lastTabId) {
    lastTabId = tab.id;
    lastScreenshotHash = null; // force send on tab switch
  }

  await captureAndSend(tab);
}

// Poll on interval
chrome.alarms.create("poll", { periodInMinutes: POLL_INTERVAL_MS / 60000 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "poll") pollActiveTab();
});

// Also fire immediately when tab is activated or updated
chrome.tabs.onActivated.addListener(({ tabId }) => {
  lastTabId = tabId;
  lastScreenshotHash = null;
  chrome.tabs.get(tabId, (tab) => { if (tab) captureAndSend(tab); });
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.active) {
    lastScreenshotHash = null;
    captureAndSend(tab);
  }
});

// Listen for DOM mutation signal from content script
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === "DOM_MUTATION" && sender.tab) {
    captureAndSend(sender.tab);
  }
});

// Initial poll
pollActiveTab();
