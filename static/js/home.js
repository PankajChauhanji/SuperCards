// Home page: create or join a room, then navigate to /room/<code>.
(function () {
  const { socket, showToast } = window.SS;

  const nameInput = document.getElementById("name");
  const codeInput = document.getElementById("code");
  const createBtn = document.getElementById("create-btn");
  const soloBtn = document.getElementById("solo-btn");
  const joinBtn = document.getElementById("join-btn");
  const gameTiles = Array.from(document.querySelectorAll(".game-tile[data-game]"));
  const settingsSections = Array.from(document.querySelectorAll(".game-settings[data-game]"));

  // Prefill saved name.
  nameInput.value = window.Identity.name();

  // ---- Game picker ----
  // Selected game_type drives create/solo and which settings block shows.
  let selectedGame = (gameTiles.find((t) => t.classList.contains("selected"))
    || gameTiles[0] || {}).dataset?.game || "super_seven";

  function syncSettingsVisibility() {
    settingsSections.forEach((sec) => {
      sec.style.display = sec.dataset.game === selectedGame ? "" : "none";
    });
  }

  gameTiles.forEach((tile) => {
    tile.addEventListener("click", () => {
      selectedGame = tile.dataset.game;
      gameTiles.forEach((t) => t.classList.toggle("selected", t === tile));
      syncSettingsVisibility();
    });
  });
  syncSettingsVisibility();

  // Each settings section has its own collapse toggle.
  settingsSections.forEach((sec) => {
    const toggle = sec.querySelector(".settings-toggle");
    const grid = sec.querySelector(".settings-grid");
    if (toggle && grid) {
      toggle.addEventListener("click", () => {
        grid.classList.toggle("hidden");
        toggle.textContent = grid.classList.contains("hidden") ? "Game settings ▸" : "Game settings ▾";
      });
    }
  });

  // Gather settings from the visible game's section (inputs carry data-key).
  function gatherSettings() {
    const sec = settingsSections.find((s) => s.dataset.game === selectedGame);
    const out = {};
    if (sec) {
      sec.querySelectorAll("input[data-key]").forEach((el) => {
        if (el.value !== "") out[el.dataset.key] = parseInt(el.value, 10);
      });
    }
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
