// Home page: create or join a room, then navigate to /room/<code>.
(function () {
  const { socket, showToast } = window.SS;

  const nameInput = document.getElementById("name");
  const codeInput = document.getElementById("code");
  const createBtn = document.getElementById("create-btn");
  const soloBtn = document.getElementById("solo-btn");
  const joinBtn = document.getElementById("join-btn");
  const settingsToggle = document.getElementById("settings-toggle");
  const settingsGrid = document.getElementById("settings-grid");
  const settingsSection = document.getElementById("settings-section");
  const gameTiles = Array.from(document.querySelectorAll(".game-tile[data-game]"));

  // Prefill saved name.
  nameInput.value = window.Identity.name();

  // ---- Game picker ----
  // Selected game_type drives create/solo and which settings block shows.
  let selectedGame = (gameTiles.find((t) => t.classList.contains("selected"))
    || gameTiles[0] || {}).dataset?.game || "super_seven";

  function syncSettingsVisibility() {
    // Show a game's settings block only when that game is selected.
    if (!settingsSection) return;
    const forGame = settingsSection.dataset.game;
    settingsSection.style.display = forGame === selectedGame ? "" : "none";
  }

  gameTiles.forEach((tile) => {
    tile.addEventListener("click", () => {
      selectedGame = tile.dataset.game;
      gameTiles.forEach((t) => t.classList.toggle("selected", t === tile));
      syncSettingsVisibility();
    });
  });
  syncSettingsVisibility();

  settingsToggle.addEventListener("click", () => {
    settingsGrid.classList.toggle("hidden");
    settingsToggle.textContent = settingsGrid.classList.contains("hidden")
      ? "Game settings ▸"
      : "Game settings ▾";
  });

  function gatherSettings() {
    const ids = ["max_score", "stop_penalty", "win_discount", "turn_timer", "timeout_limit", "num_decks"];
    const out = {};
    ids.forEach((id) => {
      const el = document.getElementById("set_" + id);
      if (el && el.value !== "") out[id] = parseInt(el.value, 10);
    });
    return out;
  }

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
      settings: gatherSettings(),
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
      settings: gatherSettings(),
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
