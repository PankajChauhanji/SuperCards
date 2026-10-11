// The join screen a shared room link opens on (partials/join_gate.html).
//
// A room link is /room/<code>. Someone who follows it without being seated is
// told so by the server (enter_room -> error reason "not_in_room"; see
// core/socket.js), and this card takes over: a name — pre-filled if this device
// already knows them — an optional avatar, and Join. Joining seats them
// (join_room) and then re-enters the room through the same resync path every
// game already uses after a reconnect, so the lobby or table simply appears
// behind the card. No page reload, no game picker, no code to type.
(function () {
  const SS = window.SS || (window.SS = {});
  const socket = SS.socket;
  const code = window.SS_ROOM_CODE;
  const gate = document.getElementById("join-gate");
  if (!gate || !socket) return;

  const nameInput = document.getElementById("jg-name");
  const joinBtn = document.getElementById("jg-join");
  const avatarsEl = document.getElementById("jg-avatars");
  let picked = "";
  let pending = false;

  function paintAvatars() {
    avatarsEl.innerHTML = "";
    [""].concat(SS.AVATARS || []).forEach((motif) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "jg-av" + (motif === picked ? " selected" : "");
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", motif === picked ? "true" : "false");
      b.setAttribute("aria-label", motif || "Use my initial");
      b.innerHTML = SS.avatarFace ? SS.avatarFace(nameInput.value.trim() || "?", motif) : "";
      b.addEventListener("click", () => { picked = motif; paintAvatars(); });
      avatarsEl.appendChild(b);
    });
  }

  function show() {
    if (!gate.hidden) return;
    nameInput.value = window.Identity ? window.Identity.name() : "";
    picked = window.Identity ? window.Identity.avatar() : "";
    paintAvatars();
    gate.hidden = false;
    document.body.classList.add("gated");
    setTimeout(() => {
      nameInput.focus();
      // Someone the device already knows is one tap away: put them on Join.
      if (nameInput.value) joinBtn.focus();
    }, 60);
  }

  function hide() {
    gate.hidden = true;
    document.body.classList.remove("gated");
  }

  function join() {
    if (pending) return;
    const name = nameInput.value.trim();
    if (!name) {
      nameInput.focus();
      if (SS.showToast) SS.showToast("Pick a name first.");
      return;
    }
    window.Identity.name(name);
    window.Identity.avatar(picked);
    pending = true;
    joinBtn.classList.add("is-loading");
    socket.emit("join_room", {
      code,
      name,
      user_id: window.Identity.userId(),
      avatar: picked,
    });
  }

  socket.on("join_ok", () => {
    if (!pending) return;
    pending = false;
    joinBtn.classList.remove("is-loading");
    hide();
    // Seated now: attach this socket and fetch the room, exactly as a
    // reconnect would.
    if (SS.resync) SS.resync();
  });
  // A refusal (table full, room closed) is shown by core/socket.js; just let
  // them try again.
  socket.on("error", () => {
    if (!pending) return;
    pending = false;
    joinBtn.classList.remove("is-loading");
  });

  joinBtn.addEventListener("click", join);
  nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") join(); });
  nameInput.addEventListener("input", () => { if (!picked) paintAvatars(); });

  SS.joinGate = { show, hide };
})();
