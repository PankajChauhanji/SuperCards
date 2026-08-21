// Connection resilience for phones.
//
// Android and iOS freeze a backgrounded page's timers and network. The phone
// comes back holding a socket that **the client still believes is open**:
// `socket.connected` reads true while the transport is already dead. Socket.IO
// only notices when a heartbeat eventually times out — and sometimes not at all.
//
// That is the bug this module exists for, and the previous version walked
// straight into it: `resume()` did nothing unless `!socket.connected`, which is
// false in exactly the zombie case. So nothing reconnected, and because state
// resync was wired only to the `connect` event, `enter_room` was never re-sent.
// Result: the player looked fine on their own screen, appeared offline to
// everyone else, could not act, and only a full page reload fixed it.
//
// The client cannot detect a dead transport locally, so on becoming visible it
// asks the server: emit `client_ping` and wait for an ack. No ack means zombie —
// tear the socket down and rebuild. An ack means the socket is genuinely fine,
// and we still resync, because a background gap may have missed broadcasts.
//
// Resync is also no longer tied to `connect` alone: SS.onResync() lets each game
// register its `enter_room` emit, and returning to the foreground runs it. That
// re-attaches this sid to the room server-side, which is what actually clears
// the "player is absent" state.
(function () {
  const SS = window.SS || (window.SS = {});
  const socket = SS.socket;
  if (!socket) return;

  // How long to wait for the liveness ack before assuming the socket is dead.
  // Generous on purpose: a needless reconnect is cheap and idempotent, whereas
  // declaring a slow-but-live socket dead would churn the connection.
  const PROBE_TIMEOUT_MS = 2500;

  let banner = null;
  let probing = false;

  function setStatus(text) {
    if (!text) {
      if (banner) {
        banner.remove();
        banner = null;
      }
      return;
    }
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "conn-banner";
      /* Announced politely — it is status, not an alert the player must act on. */
      banner.setAttribute("role", "status");
      document.body.appendChild(banner);
    }
    banner.textContent = text;
  }

  // ---- resync registry -----------------------------------------------------
  // Each game registers the emit that re-attaches it to its room. Kept as a list
  // rather than a single hook so nothing silently overwrites another game's.
  const resyncHandlers = [];

  function onResync(fn) {
    if (typeof fn === "function") resyncHandlers.push(fn);
  }

  function resync() {
    resyncHandlers.forEach((fn) => {
      try { fn(); } catch (e) { /* one bad handler must not block the others */ }
    });
  }

  // Re-render from the state we already hold. A page frozen in the background can
  // come back with stale geometry (the viewport may have changed size while the
  // JS was suspended), and the hand fan's layout is measured in JS.
  function repaintUI() {
    try {
      if (window.Table && window.Table.render && SS.view) window.Table.render(SS.view);
    } catch (e) { /* a render error must not break reconnection */ }
    try {
      if (SS.positionReactionDock) SS.positionReactionDock();
    } catch (e) { /* ditto */ }
  }

  // ---- socket lifecycle ---------------------------------------------------
  socket.on("connect", () => {
    setStatus("");
    probing = false;
  });

  socket.on("disconnect", (reason) => {
    /* Deliberate teardown (quit, page unload) — nothing to reassure anyone about. */
    if (reason === "io client disconnect") return;
    setStatus("Reconnecting…");
  });

  if (socket.io && socket.io.on) {
    socket.io.on("reconnect_attempt", () => setStatus("Reconnecting…"));
  }

  function rebuild() {
    setStatus("Reconnecting…");
    try { socket.disconnect(); } catch (e) {}
    socket.connect();
  }

  /* Ask the server whether this socket is actually alive. */
  function probe() {
    if (probing) return;
    probing = true;
    let acked = false;
    try {
      socket.emit("client_ping", null, () => { acked = true; });
    } catch (e) {
      probing = false;
      rebuild();
      return;
    }
    setTimeout(() => {
      probing = false;
      if (acked) {
        // Socket is genuinely live. Still resync: a background gap may have
        // missed broadcasts, and re-attaching is idempotent.
        setStatus("");
        resync();
        repaintUI();
      } else {
        rebuild();
      }
    }, PROBE_TIMEOUT_MS);
  }

  function resume() {
    if (document.visibilityState !== "visible") return;
    if (!socket.connected) {
      rebuild();
      return;
    }
    // Do NOT trust socket.connected here — that is the whole point of the probe.
    probe();
  }

  document.addEventListener("visibilitychange", resume);
  window.addEventListener("focus", resume);
  window.addEventListener("online", resume);
  window.addEventListener("offline", () => setStatus("No connection"));
  /* iOS restores pages from the back/forward cache without firing
     visibilitychange, so this is a separate real entry point. */
  window.addEventListener("pageshow", (e) => { if (e.persisted) resume(); else resume(); });

  SS.connection = { resume, setStatus, onResync, resync, repaintUI, probe };
  SS.onResync = onResync;
  SS.resync = resync;
  SS.repaintUI = repaintUI;
})();
