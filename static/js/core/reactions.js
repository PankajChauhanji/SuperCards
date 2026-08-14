// Shared reactions dock — emoji reactions that float up the screen.
//
// Self-initializing: reads window.SS.socket / SS_ROOM_CODE / Identity and wires
// the reaction FAB, panel, recent grid, and the incoming `reaction` event. The
// dock's show/hide (during play only) stays in each game bundle's view sync, as
// it's tied to game state. This module owns everything else — identical UX
// across every variant.
(function () {
  const SS = window.SS || (window.SS = {});
  const socket = SS.socket;
  const code = window.SS_ROOM_CODE;
  const youId = window.Identity ? window.Identity.userId() : null;
  if (!socket) return;

  const RECENT_KEY = "super_seven_recent_rx";
  const rxDock = document.getElementById("reaction-dock");
  const rxFab = document.getElementById("reaction-fab");
  const rxPanel = document.getElementById("reaction-panel");
  const rxRecentContainer = document.getElementById("rx-recent-container");
  const rxRecentGrid = document.getElementById("rx-recent-grid");

  function getRecent() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY)) || []; }
    catch (e) { return []; }
  }

  function send(emoji) {
    // Panel stays open so rapid repeat clicks can spam reactions.
    socket.emit("reaction", { code, user_id: youId, emoji });
    let recent = getRecent().filter((e) => e !== emoji);
    recent.unshift(emoji);
    if (recent.length > 5) recent.pop();
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
    updateRecentGrid();
  }

  function updateRecentGrid() {
    if (!rxRecentContainer || !rxRecentGrid) return;
    const recent = getRecent();
    if (rxFab && recent.length) rxFab.textContent = recent[0];
    if (!recent.length) { rxRecentContainer.style.display = "none"; return; }
    rxRecentContainer.style.display = "flex";
    rxRecentGrid.innerHTML = "";
    recent.forEach((emoji) => {
      const btn = document.createElement("button");
      btn.className = "rx";
      btn.dataset.e = emoji;
      btn.title = emoji;
      btn.textContent = emoji;
      btn.addEventListener("click", () => send(emoji));
      rxRecentGrid.appendChild(btn);
    });
  }

  if (rxFab && rxPanel) {
    // Single click toggles the panel; a rapid double-click fires the last-used
    // reaction immediately.
    let lastFabClick = 0, fabTimeout = null;
    rxFab.addEventListener("click", () => {
      const now = Date.now();
      const rapid = now - lastFabClick < 300;
      lastFabClick = now;
      if (rapid) {
        if (fabTimeout) { clearTimeout(fabTimeout); fabTimeout = null; }
        send(getRecent()[0] || "🤡");
      } else {
        fabTimeout = setTimeout(() => {
          fabTimeout = null;
          rxPanel.hidden = !rxPanel.hidden;
          if (!rxPanel.hidden) updateRecentGrid();
        }, 220);
      }
    });

    rxPanel.querySelectorAll("#rx-main-grid .rx").forEach((btn) =>
      btn.addEventListener("click", () => send(btn.dataset.e)));

    document.addEventListener("click", (e) => {
      if (rxDock && !rxDock.contains(e.target)) rxPanel.hidden = true;
    });

    updateRecentGrid();
  }

  function floatReaction(emoji, name) {
    const layer = document.getElementById("reactions-layer");
    if (!layer) return;
    const el = document.createElement("div");
    el.className = "rx-float";
    el.textContent = emoji;
    if (name) {
      const tag = document.createElement("span");
      tag.className = "rx-name";
      tag.textContent = name;
      el.appendChild(tag);
    }
    el.style.left = (10 + Math.random() * 70) + "%";
    el.style.setProperty("--drift", (Math.random() * 60 - 30) + "px");
    layer.appendChild(el);
    setTimeout(() => el.remove(), 3900);
  }

  socket.on("reaction", (d) => floatReaction(d.emoji, d.name));

  // Anchor the dock to the table's own bottom-right corner instead of the
  // raw viewport corner — on a wide desktop screen #table-view is centered
  // with its own max-width, so a plain `position:fixed;right;bottom` sits
  // far from the felt. Falls back to the CSS default (viewport corner) on
  // any page without #table-view (e.g. Super Four, untouched by this).
  //
  // Belt and suspenders: a ResizeObserver on #table-view catches every size
  // change generically (round start, hand dealt, opponent count, window
  // resize) without needing a call at each render site — but each game
  // bundle ALSO calls SS.positionReactionDock() directly after the render
  // calls that are known to change the felt's height (your_hand,
  // round_start, table_state), since ResizeObserver notifications can lag
  // or be throttled in a backgrounded/non-compositing tab.
  const GAP = 16;
  function positionReactionDock() {
    const tableView = document.getElementById("table-view");
    if (!rxDock || !tableView) return;
    if (getComputedStyle(tableView).display === "none") return;
    const r = tableView.getBoundingClientRect();
    rxDock.style.right = Math.max(GAP, window.innerWidth - r.right + GAP) + "px";
    rxDock.style.bottom = Math.max(GAP, window.innerHeight - r.bottom + GAP) + "px";
  }
  const tableViewEl = document.getElementById("table-view");
  if (tableViewEl && "ResizeObserver" in window) {
    new ResizeObserver(positionReactionDock).observe(tableViewEl);
  }
  window.addEventListener("resize", positionReactionDock);
  SS.positionReactionDock = positionReactionDock;
})();
