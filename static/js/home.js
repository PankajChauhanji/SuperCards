// Home page: who you are, join a table by code, or start one, then navigate to
// /room/<code>. Round settings are NOT set here — the server fills defaults and
// the host tunes them in the lobby.
(function () {
  const { socket, showToast } = window.SS;
  const $ = (id) => document.getElementById(id);

  const codeInput = $("code");
  const createBtn = $("create-btn");
  const soloBtn = $("solo-btn");
  const joinBtn = $("join-btn");
  const gameTiles = Array.from(document.querySelectorAll(".game-tile[data-game]"));

  // The shared avatar list (core/icons.js), checked against the server's.
  const MOTIFS = window.SS.AVATARS || [];

  // ---- who you are ----
  function paintIdentity() {
    const name = window.Identity.name();
    $("profile-name").textContent = name || "Set your name";
    $("profile-btn").classList.toggle("unset", !name);
    $("profile-av").innerHTML = window.SS.avatarFace(name || "?", window.Identity.avatar());
  }

  // ---- the player dialog ----
  const modal = $("profile-modal");
  const nameInput = $("name");
  const grid = $("avatar-grid");
  let pickedAvatar = "";
  let afterSave = null;   // the action that was waiting for a name

  function paintGrid() {
    grid.innerHTML = "";
    const options = [""].concat(MOTIFS);
    options.forEach((motif) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "av-opt" + (motif === pickedAvatar ? " selected" : "");
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", motif === pickedAvatar ? "true" : "false");
      b.setAttribute("aria-label", motif ? motif : "Use my initial");
      b.title = motif ? motif.charAt(0).toUpperCase() + motif.slice(1) : "Your initial";
      b.innerHTML = window.SS.avatarFace(nameInput.value.trim() || window.Identity.name() || "?", motif);
      b.addEventListener("click", () => { pickedAvatar = motif; paintGrid(); });
      grid.appendChild(b);
    });
  }

  function openProfile(note, then) {
    afterSave = then || null;
    nameInput.value = window.Identity.name();
    pickedAvatar = window.Identity.avatar();
    $("profile-note").textContent = note ||
      "This is how the table will see you. It's saved on this device — no account needed.";
    paintGrid();
    modal.classList.add("open");
    setTimeout(() => nameInput.focus(), 50);
  }
  function closeProfile() {
    modal.classList.remove("open");
    afterSave = null;
  }
  function saveProfile() {
    const name = nameInput.value.trim();
    if (!name) { nameInput.focus(); return showToast("Pick a name first."); }
    window.Identity.name(name);
    window.Identity.avatar(pickedAvatar);
    paintIdentity();
    const next = afterSave;
    afterSave = null;
    modal.classList.remove("open");
    if (next) next();
  }

  $("profile-btn").addEventListener("click", () => openProfile());
  $("profile-save").addEventListener("click", saveProfile);
  $("profile-cancel").addEventListener("click", closeProfile);
  nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") saveProfile(); });
  // The initial option previews the typed name live.
  nameInput.addEventListener("input", () => { if (!pickedAvatar) paintGrid(); });
  modal.addEventListener("click", (e) => { if (e.target === modal) closeProfile(); });

  // Any action that needs a name asks for one first, then carries on.
  function withName(action) {
    if (window.Identity.name()) return action();
    openProfile("First, what should the table call you?", action);
  }

  // ---- game picker ----
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

  function lockButtons(locked, which) {
    [createBtn, soloBtn, joinBtn].forEach((b) => {
      b.disabled = locked;
      b.classList.toggle("is-loading", locked && b === which);
    });
  }

  function payload(extra) {
    return Object.assign({
      name: window.Identity.name(),
      user_id: window.Identity.userId(),
      avatar: window.Identity.avatar(),
    }, extra);
  }

  createBtn.addEventListener("click", () => withName(() => {
    lockButtons(true, createBtn);
    socket.emit("create_room", payload({ game_type: selectedGame }));
  }));

  soloBtn.addEventListener("click", () => withName(() => {
    lockButtons(true, soloBtn);
    socket.emit("create_solo", payload({ game_type: selectedGame }));
  }));

  function join() {
    const code = codeInput.value.trim().toUpperCase();
    if (code.length !== 4) { codeInput.focus(); return showToast("Room codes are 4 letters."); }
    withName(() => {
      lockButtons(true, joinBtn);
      socket.emit("join_room", payload({ code }));
    });
  }
  joinBtn.addEventListener("click", join);
  codeInput.addEventListener("keydown", (e) => { if (e.key === "Enter") join(); });
  codeInput.addEventListener("input", () => {
    codeInput.value = codeInput.value.replace(/[^a-z]/gi, "").toUpperCase().slice(0, 4);
    $("join-card").classList.toggle("ready", codeInput.value.length === 4);
  });

  // ---- links that land here ----
  // /?join=ABCD (older invites): the room page itself now asks for a name and
  // seats the player, so send them straight there.
  const params = new URLSearchParams(window.location.search);
  const invited = (params.get("join") || "").replace(/[^a-z]/gi, "").toUpperCase().slice(0, 4);
  if (invited.length === 4) {
    window.location.replace("/room/" + invited);
    return;
  }
  // /?gone=ABCD: a room link for a table that has already closed.
  const gone = (params.get("gone") || "").replace(/[^a-z]/gi, "").toUpperCase().slice(0, 4);
  if (gone) {
    if (window.history.replaceState) window.history.replaceState(null, "", "/");
    setTimeout(() => showToast("Table " + gone + " has closed. Start a new one, or ask for a fresh code.", 5000), 300);
  }

  socket.on("room_created", (data) => {
    window.location.href = "/room/" + data.code;
  });

  socket.on("join_ok", (data) => {
    window.location.href = "/room/" + data.code;
  });

  // Re-enable buttons if the server rejected the action.
  socket.on("error", () => lockButtons(false));

  // ---- About dialog (footer) ----
  const aboutModal = $("about-modal");
  const aboutLink = $("about-link");
  if (aboutModal && aboutLink) {
    const close = () => aboutModal.classList.remove("open");
    aboutLink.addEventListener("click", () => aboutModal.classList.add("open"));
    $("about-close").addEventListener("click", close);
    aboutModal.addEventListener("click", (e) => { if (e.target === aboutModal) close(); });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (aboutModal) aboutModal.classList.remove("open");
    if (modal.classList.contains("open")) closeProfile();
  });

  paintIdentity();
})();
