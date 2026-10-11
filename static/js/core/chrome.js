// Shared lobby chrome bits: copy-room-code, the scores-panel collapse, and the
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

  // Sound lives in core/settings.js now: the topbar button and the Settings
  // switch are one setting, so one module paints both.

  // ---- copy room code ----
  const copyBtn = document.getElementById("copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(code);
        showToast("Room code copied", 0, "success");
      } catch (_) {
        showToast("Code: " + code);
      }
    });
  }

  // ---- scores panel collapse ----
  // Unlike Action History (action_log.js), this stays open by default at
  // every width — it carries the turn indicator, so hiding it automatically
  // on phones would cost more than the space it saves.
  const scoresPanel = document.getElementById("sb-players");
  const scoresToggle = document.getElementById("scores-toggle");
  if (scoresPanel && scoresToggle) {
    const toggleScores = () => {
      const collapsed = scoresPanel.classList.toggle("is-collapsed");
      scoresToggle.setAttribute("aria-expanded", String(!collapsed));
    };
    scoresToggle.addEventListener("click", toggleScores);
    scoresToggle.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleScores(); }
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
