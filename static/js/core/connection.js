// Connection resilience for phones.
//
// Android freezes a backgrounded WebView's timers and network. A phone that has
// been in a pocket comes back holding a socket the client still believes is
// open; Socket.IO only notices once a heartbeat times out, which is several
// seconds of a table that looks alive but is not. Re-checking the moment the
// page becomes visible makes the resume feel instant.
//
// State resync is already handled: every game bundle re-emits `enter_room` on
// "connect". This module only has to make the reconnect happen promptly and
// tell the player what is going on while it does.
(function () {
  const socket = window.SS && window.SS.socket;
  if (!socket) return;

  let banner = null;

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

  socket.on("connect", () => setStatus(""));

  socket.on("disconnect", (reason) => {
    /* Deliberate teardown (quit, page unload) — nothing to reassure anyone about. */
    if (reason === "io client disconnect") return;
    setStatus("Reconnecting…");
  });

  if (socket.io && socket.io.on) {
    socket.io.on("reconnect_attempt", () => setStatus("Reconnecting…"));
  }

  /* Nudge a stalled socket awake. Safe to call when a reconnect is already in
     flight — Socket.IO ignores connect() on an open or connecting manager. */
  function resume() {
    if (document.visibilityState !== "visible") return;
    if (!socket.connected) {
      setStatus("Reconnecting…");
      socket.connect();
    }
  }

  document.addEventListener("visibilitychange", resume);
  window.addEventListener("focus", resume);
  window.addEventListener("online", resume);
  window.addEventListener("offline", () => setStatus("No connection"));

  window.SS = window.SS || {};
  window.SS.connection = { resume, setStatus };
})();
