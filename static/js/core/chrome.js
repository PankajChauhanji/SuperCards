// Shared topbar/lobby chrome bits: mute toggle, copy-room-code, and the
// host's spectator-admit modal. All self-wiring and game-agnostic.
//
// The spectator-admit flow is exposed as SS.openSpectatorModal(targetId, name),
// called by a game's scoreboard/roster when the host clicks "admit".
(function () {
  const SS = window.SS || (window.SS = {});
  const socket = SS.socket;
  const code = window.SS_ROOM_CODE;
  const youId = window.Identity ? window.Identity.userId() : null;
  const showToast = SS.showToast || function () {};

  // ---- mute toggle ----
  const muteBtn = document.getElementById("mute-btn");
  if (muteBtn && SS.sound) {
    const paint = () => { muteBtn.textContent = SS.sound.muted() ? "🔇" : "🔊"; };
    paint();
    muteBtn.addEventListener("click", () => { SS.sound.toggleMute(); paint(); });
  }

  // ---- copy room code ----
  const copyBtn = document.getElementById("copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(code);
        showToast("Room code copied.");
      } catch (_) {
        showToast("Code: " + code);
      }
    });
  }

  // ---- mobile topbar menu (hamburger) ----
  // On narrow widths the action controls (sound/theme/rules/quit) collapse into
  // this dropdown; on desktop they sit inline and the hamburger is hidden (CSS).
  const menuBtn = document.getElementById("topbar-menu-btn");
  const menuPanel = document.getElementById("topbar-actions");
  if (menuBtn && menuPanel) {
    const setOpen = (open) => {
      menuPanel.classList.toggle("open", open);
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    };
    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      setOpen(!menuPanel.classList.contains("open"));
    });
    // Close when tapping outside, or after choosing Rules/Quit (which navigate
    // away or open a modal). Sound/theme keep the menu open for repeat use.
    document.addEventListener("click", (e) => {
      if (menuPanel.classList.contains("open") &&
          !menuPanel.contains(e.target) && e.target !== menuBtn) {
        setOpen(false);
      }
    });
    ["rules-btn", "quit-btn"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("click", () => setOpen(false));
    });
  }

  // ---- spectator admit modal (host) ----
  const specModal = document.getElementById("spectator-modal");
  const specCancel = document.getElementById("admit-cancel");
  const specConfirm = document.getElementById("admit-confirm");
  let admitTargetId = null;

  SS.openSpectatorModal = function (targetId, name) {
    if (!specModal) return;
    admitTargetId = targetId;
    const nameEl = document.getElementById("admit-name");
    const penaltyEl = document.getElementById("admit-penalty");
    if (nameEl) nameEl.textContent = name;
    if (penaltyEl) penaltyEl.value = "0";
    specModal.classList.add("open");
  };

  if (specCancel) {
    specCancel.addEventListener("click", () => {
      if (specModal) specModal.classList.remove("open");
      admitTargetId = null;
    });
  }
  if (specConfirm) {
    specConfirm.addEventListener("click", () => {
      if (admitTargetId && socket) {
        const penalty = parseInt(document.getElementById("admit-penalty").value, 10) || 0;
        socket.emit("admit_spectator", { code, user_id: youId, target_id: admitTargetId, penalty });
      }
      if (specModal) specModal.classList.remove("open");
      admitTargetId = null;
    });
  }
})();
