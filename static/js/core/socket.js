// Thin wrapper around the Socket.IO connection plus a shared toast for errors.
(function () {
  const socket = io();

  // Standard error channel from the server — the one place toasts are red.
  socket.on("error", (data) => {
    // Someone opened a shared /room/<code> link without joining first: ask for
    // their name right here (core/join_gate.js) and seat them, rather than
    // leave them on a table they are not part of.
    if (data && data.reason === "not_in_room" && window.SS_ROOM_CODE) {
      if (window.SS && window.SS.joinGate) window.SS.joinGate.show();
      else window.location.replace("/");
      return;
    }
    // This window's seat was not on file when it acted (sockets/seat_guard.py) —
    // in practice a reconnect race. Re-enter the room, which re-seats it.
    if (data && data.reason === "not_your_seat") {
      if (window.SS && window.SS.resync) window.SS.resync();
      showToast("Reconnected to your seat — try that again.", 3000);
      return;
    }
    showToast((data && data.message) || "Something went wrong.", 0, "error");
  });

  // kind: "info" (default) | "success" | "error". Every toast used to be the
  // accent red, so "Settings saved" looked exactly like a refusal. Callers that
  // pass only (message, ms) keep working and get the neutral style.
  const TOAST_ICONS = { info: "info", success: "check-circle", error: "alert" };
  let toastTimer = null;
  function showToast(message, ms, kind) {
    let el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      document.body.appendChild(el);
    }
    kind = TOAST_ICONS[kind] ? kind : "info";
    el.className = "toast-" + kind;
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    const icon = window.SS && window.SS.icon ? window.SS.icon(TOAST_ICONS[kind]) : "";
    el.innerHTML = icon + '<span class="toast-text"></span>';
    el.querySelector(".toast-text").textContent = message;
    // Restart the entrance even when one toast replaces another.
    void el.offsetWidth;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), ms || 3200);
  }

  /* Merge, don't replace — modules that registered on SS before this one loads
     (e.g. core/install.js, which runs from <head>) would otherwise be wiped. */
  window.SS = window.SS || {};
  Object.assign(window.SS, { socket, showToast });
})();
