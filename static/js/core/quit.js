// Quit Game — lets a player leave the room voluntarily at any time.
//
// Quitting removes only this player: their instance and scores are dropped and
// the game continues for everyone else. If the host quits, the server promotes
// a new host. If only one player would remain, the server ends the game and
// declares that player the winner. Shared across all game variants.
//
// Also owns the Android back button. In the installed app there is no browser
// chrome to fall back on, so an unguarded back press drops the player out of a
// live game with no warning and no way to undo it. A sentinel history entry
// catches the first press and routes it through the same confirmation as the
// Quit button.
(function () {
  const btn = document.getElementById("quit-btn");
  if (!btn) return;

  const socket = window.SS && window.SS.socket;
  const code = window.SS_ROOM_CODE;
  const CONFIRM = {
    title: "Leave this table?",
    message: "You'll be removed and your score cleared. The game carries on for everyone else.",
    confirmLabel: "Leave table",
    cancelLabel: "Stay",
    danger: true,
  };
  // The app's own dialog (core/dialog.js); the browser box only as a fallback.
  function ask() {
    if (window.SS && window.SS.confirm) return window.SS.confirm(CONFIRM);
    return Promise.resolve(window.confirm(CONFIRM.title + "\n\n" + CONFIRM.message));
  }

  let leaving = false;

  function go() {
    window.location.href = "/";
  }

  function doQuit() {
    if (leaving) return;
    leaving = true;
    const userId = window.Identity ? window.Identity.userId() : null;
    if (socket && userId) {
      socket.emit("quit_game", { code: code, user_id: userId });
      // Fallback in case the server never acks (e.g. dropped connection).
      setTimeout(go, 1500);
    } else {
      go();
    }
  }

  btn.addEventListener("click", () => {
    if (leaving) return;
    if (window.SS && window.SS.settings) window.SS.settings.close();
    ask().then((ok) => { if (ok) doQuit(); });
  });

  if (socket) socket.on("quit_ok", go);

  /* ── Back-button guard ────────────────────────────────────────────── */

  let guarded = false;

  function arm() {
    if (guarded || leaving) return;
    history.pushState({ ssGuard: true }, "");
    guarded = true;
  }

  window.addEventListener("popstate", () => {
    /* The sentinel has been consumed by this press. */
    guarded = false;
    if (leaving) return;
    /* Not seated yet (the join screen is up): there is nothing to leave. */
    if (document.body.classList.contains("gated")) { go(); return; }
    ask().then((ok) => {
      if (ok) doQuit();
      /* Stay put — put the sentinel back so the next press asks again. */
      else arm();
    });
  });

  arm();
})();
