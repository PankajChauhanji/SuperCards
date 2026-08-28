// Connection resilience: keep this client's table equal to the server's truth.
//
// Two things go wrong on a real phone that never go wrong in a desktop
// mobile-emulation view, which is why this was only ever reported from actual
// devices and installed apps:
//
//   1. The transport dies without the client being told. Android and iOS freeze
//      a backgrounded page's timers and network, so the page comes back holding
//      a socket it still believes is open — `socket.connected` reads true while
//      nothing is flowing. The server, whose timers never froze, already timed
//      that session out and marked the player offline. The player then sits on a
//      table that never updates while everyone else watches them time out.
//
//   2. The client misses a broadcast and never finds out. Every event carries a
//      full snapshot, so one miss is normally corrected by the next event — but
//      if the table is now waiting on *this* player, there is no next event. The
//      game stalls on someone whose screen never told them it was their turn.
//
// The previous version probed for (1) on `visibilitychange` alone, which covers
// exactly one entry point: the phone coming out of a pocket. A socket that died
// while the player was looking at the screen — a Wi-Fi/cellular handoff, a lift,
// a dropped packet — was never re-checked, and (2) was not detected at all.
//
// So the check is now a heartbeat rather than an event. While the page is
// visible, `client_sync` goes out on a timer carrying the last state version
// this client has seen, and the answer settles all of it:
//
//   * the ack arriving proves the socket is alive end-to-end — no ack means a
//     zombie, so tear it down and rebuild;
//   * `stale` means the server does not have this socket on file, so re-enter;
//   * `v` disagreeing with ours means we missed something, so re-enter.
//
// The cure in every case is `enter_room`, which already re-attaches the socket
// server-side and replays full state. See sockets/sync.py for the other half.
(function () {
  const SS = window.SS || (window.SS = {});
  const socket = SS.socket;
  if (!socket) return;

  // How long to wait for the ack before assuming the socket is dead. Generous
  // on purpose: a needless reconnect is cheap and idempotent, whereas declaring
  // a slow-but-live socket dead would churn the connection on a weak signal.
  const PROBE_TIMEOUT_MS = 2500;
  // Heartbeat period. Short enough that a stall is corrected inside one turn,
  // long enough to be invisible next to gameplay traffic — the payload is three
  // short strings and an integer.
  const HEARTBEAT_MS = 10000;

  // Room pages only. connection.js also loads on the landing page, where there
  // is no room to be out of sync with.
  const roomCode = window.SS_ROOM_CODE || null;

  let banner = null;
  let heartbeat = null;
  // Highest state version this client has seen. Only ever advances: an ack can
  // be in flight while a newer broadcast lands, and adopting the older number
  // would make us re-enter for nothing on the next beat.
  let stateVersion = -1;
  // The in-flight probe's timeout, so it can be cancelled. Leaving it to fire
  // was its own bug: after the socket recovered on its own, the stale timer
  // still saw "no ack" and tore down the healthy connection, which the server
  // reads as a real disconnect — the player flashed offline to the whole table.
  let probeTimer = null;

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
  // Each game registers the emit that re-attaches it to its room (`enter_room`).
  // Kept as a list rather than a single hook so nothing silently overwrites
  // another game's.
  const resyncHandlers = [];

  function onResync(fn) {
    if (typeof fn === "function") resyncHandlers.push(fn);
  }

  function resync() {
    resyncHandlers.forEach((fn) => {
      try { fn(); } catch (e) { /* one bad handler must not block the others */ }
    });
  }

  // ---- repaint registry ----------------------------------------------------
  // Re-render from the state we already hold, without asking the server. A page
  // frozen in the background can come back with stale geometry, because the
  // viewport may have resized (the URL bar collapsing) while the JS was
  // suspended and the hand fan's layout is measured in JS. Also used by the deck
  // and hand-view pickers.
  //
  // This is a registry rather than a direct call to `window.Table.render`
  // because that shape is Super Seven's and Bluff's. Super 4 renders its own
  // table and defines neither `window.Table` nor `SS.view`, so the old direct
  // call silently did nothing there — its players had to reload the page for a
  // deck change to appear. Every bundle now registers its own repaint, so no
  // shared code has to guess at a game's render entry point.
  const repaintHandlers = [];

  function onRepaint(fn) {
    if (typeof fn === "function") repaintHandlers.push(fn);
  }

  function repaintUI() {
    repaintHandlers.forEach((fn) => {
      try {
        fn();
      } catch (e) {
        /* A render error must not break reconnection — but it must not be
           invisible either. A silently swallowed repaint is precisely how a
           broken table survives unnoticed until someone reports it from a
           phone. */
        console.warn("repaint handler failed", e);
      }
    });
    try {
      if (SS.positionReactionDock) SS.positionReactionDock();
    } catch (e) {
      console.warn("reaction dock reposition failed", e);
    }
  }

  // ---- state version -------------------------------------------------------
  // Every room-wide broadcast is numbered by the server (sockets/audience.py).
  // Reading it from a catch-all listener means no game has to know this exists,
  // and a new event type is covered the day it is added.
  if (socket.onAny) {
    socket.onAny((_event, payload) => {
      if (payload && typeof payload._v === "number" && payload._v > stateVersion) {
        stateVersion = payload._v;
      }
    });
  }

  // ---- socket lifecycle ----------------------------------------------------
  function cancelProbe() {
    if (probeTimer !== null) {
      clearTimeout(probeTimer);
      probeTimer = null;
    }
  }

  socket.on("connect", () => {
    setStatus("");
    /* A fresh socket has a fresh server session; the old probe's verdict is
       about a connection that no longer exists. */
    cancelProbe();
    /* Re-entry will tell us the current version; until then, claim nothing. */
    stateVersion = -1;
  });

  socket.on("disconnect", (reason) => {
    cancelProbe();
    /* Deliberate teardown (quit, page unload) — nothing to reassure anyone about. */
    if (reason === "io client disconnect") return;
    setStatus("Reconnecting…");
  });

  if (socket.io && socket.io.on) {
    socket.io.on("reconnect_attempt", () => setStatus("Reconnecting…"));
  }

  function rebuild() {
    setStatus("Reconnecting…");
    cancelProbe();
    try { socket.disconnect(); } catch (e) {}
    socket.connect();
  }

  /* One heartbeat: prove the socket is alive, and find out whether our state is. */
  function beat() {
    if (!roomCode || probeTimer !== null) return;

    let settled = false;
    probeTimer = setTimeout(() => {
      if (settled) return;
      settled = true;
      probeTimer = null;
      /* No answer in the window: the transport is dead however alive it looks. */
      rebuild();
    }, PROBE_TIMEOUT_MS);

    const payload = {
      code: roomCode,
      user_id: window.Identity ? window.Identity.userId() : null,
      v: stateVersion,
    };

    try {
      socket.emit("client_sync", payload, (ack) => {
        if (settled) return;
        settled = true;
        cancelProbe();
        setStatus("");
        if (!ack || !ack.room) return;
        /* Adopt the server's number before deciding, so a re-entry triggered
           here cannot immediately trigger another one. */
        const behind = typeof ack.v === "number" && ack.v !== stateVersion;
        if (typeof ack.v === "number" && ack.v > stateVersion) stateVersion = ack.v;
        if (ack.stale || behind) {
          resync();
          repaintUI();
        }
      });
    } catch (e) {
      /* Emitting threw, so nothing is coming back. Do not wait for the timer. */
      settled = true;
      cancelProbe();
      rebuild();
    }
  }

  function startHeartbeat() {
    if (heartbeat !== null || !roomCode) return;
    heartbeat = setInterval(beat, HEARTBEAT_MS);
  }

  function stopHeartbeat() {
    if (heartbeat === null) return;
    clearInterval(heartbeat);
    heartbeat = null;
  }

  /* Coming back to the page: check immediately rather than waiting a beat, and
     repaint, because the viewport may have changed while the JS was suspended. */
  function resume() {
    if (document.visibilityState !== "visible") return;
    startHeartbeat();
    if (!socket.connected) {
      rebuild();
      return;
    }
    // Do NOT trust socket.connected — that it lies is the whole reason for the
    // heartbeat.
    beat();
    repaintUI();
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      resume();
    } else {
      /* Backgrounded timers are throttled to the point of uselessness anyway,
         and a beat that fires late would probe a connection nobody is watching. */
      stopHeartbeat();
      cancelProbe();
    }
  });
  window.addEventListener("focus", resume);
  window.addEventListener("online", resume);
  window.addEventListener("offline", () => setStatus("No connection"));
  /* iOS restores pages from the back/forward cache without firing
     visibilitychange, so this is a separate real entry point. */
  window.addEventListener("pageshow", resume);

  if (document.visibilityState === "visible") startHeartbeat();

  SS.connection = { resume, setStatus, onResync, resync, onRepaint, repaintUI, beat };
  SS.onResync = onResync;
  SS.resync = resync;
  SS.onRepaint = onRepaint;
  SS.repaintUI = repaintUI;
})();
