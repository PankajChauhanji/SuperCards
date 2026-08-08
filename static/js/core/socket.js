// Thin wrapper around the Socket.IO connection plus a shared toast for errors.
(function () {
  const socket = io();

  // Standard error channel from the server.
  socket.on("error", (data) => {
    showToast((data && data.message) || "Something went wrong.");
  });

  let toastTimer = null;
  function showToast(message, ms) {
    let el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), ms || 3200);
  }

  /* Merge, don't replace — modules that registered on SS before this one loads
     (e.g. core/install.js, which runs from <head>) would otherwise be wiped. */
  window.SS = window.SS || {};
  Object.assign(window.SS, { socket, showToast });
})();
