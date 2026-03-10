// content.js — injected into every page
// Manages the overlay tile system and signals significant DOM mutations.

(function () {
  if (window.__uiNavigatorLoaded) return;
  window.__uiNavigatorLoaded = true;

  // Inject overlay container
  const container = document.createElement("div");
  container.id = "ui-navigator-overlay";
  document.body.appendChild(container);

  // ---- Tile Manager ----
  const MAX_TILES = 3;
  let tiles = []; // { id, title, summary, icon, url }
  let dismissedIds = new Set();
  let currentUrl = location.href;

  function renderTiles() {
    container.innerHTML = "";
    tiles.forEach((tile) => {
      const el = document.createElement("div");
      el.className = "ui-nav-tile";
      el.dataset.id = tile.id;
      el.innerHTML = `
        <div class="ui-nav-tile-header">
          <span class="ui-nav-tile-icon">${tile.icon || "💡"}</span>
          <span class="ui-nav-tile-title">${escapeHtml(tile.title)}</span>
          <button class="ui-nav-dismiss" aria-label="Dismiss">×</button>
        </div>
        <div class="ui-nav-tile-body">${escapeHtml(tile.summary)}</div>
        ${tile.link ? `<a class="ui-nav-tile-link" href="${escapeHtml(tile.link)}" target="_blank" rel="noopener">Learn more →</a>` : ""}
      `;
      el.querySelector(".ui-nav-dismiss").addEventListener("click", () => dismiss(tile.id));
      container.appendChild(el);
    });
  }

  function dismiss(id) {
    dismissedIds.add(id);
    tiles = tiles.filter((t) => t.id !== id);
    renderTiles();
  }

  function addCards(newCards, url) {
    // Reset dismissed set if URL changed
    if (url !== currentUrl) {
      dismissedIds = new Set();
      currentUrl = url;
    }

    newCards.forEach((card) => {
      if (dismissedIds.has(card.id)) return;
      // Remove existing tile with same id (update in place)
      tiles = tiles.filter((t) => t.id !== card.id);
      tiles.unshift(card); // newest first
    });

    // Keep only MAX_TILES
    tiles = tiles.slice(0, MAX_TILES);
    renderTiles();
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ---- Listen for cards from background ----
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "NEW_CARDS") {
      addCards(msg.cards, msg.url);
    }
  });

  // ---- Signal DOM mutations to background ----
  let mutationTimer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(mutationTimer);
    mutationTimer = setTimeout(() => {
      chrome.runtime.sendMessage({ type: "DOM_MUTATION" }).catch(() => {});
    }, 1500); // debounce: wait 1.5s after mutations settle
  });

  observer.observe(document.body, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ["value", "checked", "selected"]
  });
})();
