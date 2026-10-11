// SS.confirm({ title, message, confirmLabel, cancelLabel, danger }) -> Promise<boolean>
//
// The app's own confirmation dialog, replacing window.confirm(). The browser's
// box is unstyled, shows the site's address as its title, and on Android looks
// like a system warning — the opposite of a game asking "are you sure?".
//
// One dialog is built on first use and reused. Escape, the backdrop and Cancel
// all resolve false; only the confirm button resolves true. Focus goes to
// Cancel, so a stray Enter never confirms something destructive.
(function () {
  const SS = window.SS || (window.SS = {});
  let el = null;
  let settle = null;

  function build() {
    el = document.createElement("div");
    el.className = "modal-backdrop";
    el.id = "confirm-modal";
    el.innerHTML =
      '<div class="modal confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-msg">' +
        '<h2 id="confirm-title"></h2>' +
        '<p id="confirm-msg"></p>' +
        '<div class="close-row">' +
          '<button type="button" class="btn-ghost" id="confirm-cancel"></button>' +
          '<button type="button" id="confirm-ok"></button>' +
        "</div>" +
      "</div>";
    document.body.appendChild(el);
    el.addEventListener("click", (e) => { if (e.target === el) done(false); });
    el.querySelector("#confirm-cancel").addEventListener("click", () => done(false));
    el.querySelector("#confirm-ok").addEventListener("click", () => done(true));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && el.classList.contains("open")) done(false);
    });
  }

  function done(result) {
    if (!el) return;
    el.classList.remove("open");
    const fn = settle;
    settle = null;
    if (fn) fn(result);
  }

  SS.confirm = function (opts) {
    opts = opts || {};
    if (!el) build();
    if (settle) done(false);   // a newer question replaces an unanswered one
    el.querySelector("#confirm-title").textContent = opts.title || "Are you sure?";
    el.querySelector("#confirm-msg").textContent = opts.message || "";
    const ok = el.querySelector("#confirm-ok");
    ok.textContent = opts.confirmLabel || "Confirm";
    ok.className = opts.danger ? "btn-danger solid" : "btn-primary";
    el.querySelector("#confirm-cancel").textContent = opts.cancelLabel || "Cancel";
    el.classList.add("open");
    el.querySelector("#confirm-cancel").focus({ preventScroll: true });
    return new Promise((resolve) => { settle = resolve; });
  };
})();
