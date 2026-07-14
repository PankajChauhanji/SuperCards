// Thin wrapper around the Socket.IO connection plus a shared toast for errors.
(function () {
  const socket = io();

  // Standard error channel from the server.
  socket.on("error", (data) => {
    showToast((data && data.message) || "Something went wrong.");
  });

  let toastTimer = null;
  function showToast(message) {
    let el = document.getElementById("toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  window.SS = { socket, showToast };
})();
