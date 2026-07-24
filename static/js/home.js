// Home page: choose a game, create or join a room, then navigate to /room/<code>.
// Round settings are NOT set here — the server fills defaults and the host tunes
// them in the lobby.
(function () {
  const { socket, showToast } = window.SS;

  const nameInput = document.getElementById("name");
  const codeInput = document.getElementById("code");
  const createBtn = document.getElementById("create-btn");
  const soloBtn = document.getElementById("solo-btn");
  const joinBtn = document.getElementById("join-btn");
  const gameTiles = Array.from(document.querySelectorAll(".game-tile[data-game]"));

  // Prefill saved name.
  nameInput.value = window.Identity.name();

  // ---- Game picker ----
  // The selected game_type drives create / solo.
  let selectedGame = (gameTiles.find((t) => t.classList.contains("selected"))
    || gameTiles[0] || {}).dataset?.game || "super_seven";

  gameTiles.forEach((tile) => {
    tile.addEventListener("click", () => {
      selectedGame = tile.dataset.game;
      gameTiles.forEach((t) => {
        const on = t === tile;
        t.classList.toggle("selected", on);
        t.setAttribute("aria-checked", on ? "true" : "false");
      });
    });
  });

  function lockButtons(locked) {
    createBtn.disabled = locked;
    soloBtn.disabled = locked;
    joinBtn.disabled = locked;
  }

  createBtn.addEventListener("click", () => {
    const name = nameInput.value.trim();
    if (!name) return showToast("Pick a name first.");
    window.Identity.name(name);
    lockButtons(true);
    socket.emit("create_room", {
      name,
      user_id: window.Identity.userId(),
      game_type: selectedGame,
    });
  });

  soloBtn.addEventListener("click", () => {
    const name = nameInput.value.trim();
    if (!name) return showToast("Pick a name first.");
    window.Identity.name(name);
    lockButtons(true);
    socket.emit("create_solo", {
      name,
      user_id: window.Identity.userId(),
      game_type: selectedGame,
    });
  });

  joinBtn.addEventListener("click", () => {
    const name = nameInput.value.trim();
    const code = codeInput.value.trim().toUpperCase();
    if (!name) return showToast("Pick a name first.");
    if (code.length !== 4) return showToast("Room codes are 4 letters.");
    window.Identity.name(name);
    lockButtons(true);
    socket.emit("join_room", { code, name, user_id: window.Identity.userId() });
  });

  // Enter key on the code field triggers join.
  codeInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") joinBtn.click();
  });

  socket.on("room_created", (data) => {
    window.location.href = "/room/" + data.code;
  });

  socket.on("join_ok", (data) => {
    window.location.href = "/room/" + data.code;
  });

  // Re-enable buttons if the server rejected the action.
  socket.on("error", () => lockButtons(false));
})();
