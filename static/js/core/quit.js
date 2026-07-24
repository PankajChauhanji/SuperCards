// Quit Game — lets a player leave the room voluntarily at any time.
//
// Quitting removes only this player: their instance and scores are dropped and
// the game continues for everyone else. If the host quits, the server promotes
// a new host. If only one player would remain, the server ends the game and
// declares that player the winner. Shared across all game variants.
(function () {
  const btn = document.getElementById("quit-btn");
  if (!btn) return;

  const socket = window.SS && window.SS.socket;
  const code = window.SS_ROOM_CODE;
  let leaving = false;

  function go() {
    window.location.href = "/";
  }

  btn.addEventListener("click", () => {
    if (leaving) return;
    const ok = window.confirm(
      "Quit this game?\n\nYou'll be removed and your scores cleared. The game keeps going for everyone else."
    );
    if (!ok) return;
    leaving = true;
    const userId = window.Identity ? window.Identity.userId() : null;
    if (socket && userId) {
      socket.emit("quit_game", { code: code, user_id: userId });
      // Fallback in case the server never acks (e.g. dropped connection).
      setTimeout(go, 1500);
    } else {
      go();
    }
  });

  if (socket) socket.on("quit_ok", go);
})();
