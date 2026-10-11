// Shared "Standard view / Box view" hand-display preference.
//
// Unlike the table theme, this is a personal, per-device choice — not
// host-controlled, not synced over the socket. Standard is the fanned,
// held-like-real-cards layout; Box is a flat, non-overlapping, scrollable
// grid (core/seats.js layoutHandGrid) for hands too big to fan on any
// screen size (Bluff can run to 50+ cards for one player in a 2-player
// game). Super Seven defaults to Standard (always exactly 7 cards); Bluff
// defaults to Box. Super Four has only one hand layout and never shows
// this control at all.
//
// The picker is a section of the Settings sheet.
(function () {
  const SS = window.SS || (window.SS = {});
  const STORAGE_PREFIX = "super_cards_view_mode_";
  const DEFAULTS = { super_seven: "standard", bluff: "box" };

  function get(gameType) {
    try {
      const stored = localStorage.getItem(STORAGE_PREFIX + gameType);
      if (stored === "standard" || stored === "box") return stored;
    } catch (e) {
      /* localStorage unavailable (private mode etc.) — fall through to default */
    }
    return DEFAULTS[gameType] || "standard";
  }

  function set(gameType, mode) {
    try { localStorage.setItem(STORAGE_PREFIX + gameType, mode); } catch (e) {}
  }

  SS.viewMode = { get, set };

  const gameType = window.GAME_TYPE;
  const wrap = document.getElementById("view-mode-wrap");
  if (!wrap || gameType === "super_four") return;
  wrap.hidden = false;

  // A section of the Settings sheet (partials/view_mode_selector.html).
  const opts = Array.from(wrap.querySelectorAll(".seg-opt[data-mode]"));
  function mark(mode) {
    opts.forEach((opt) => {
      const on = opt.dataset.mode === mode;
      opt.classList.toggle("selected", on);
      opt.setAttribute("aria-checked", on ? "true" : "false");
    });
  }
  mark(get(gameType));

  opts.forEach((opt) => {
    opt.addEventListener("click", () => {
      const mode = opt.dataset.mode;
      set(gameType, mode);
      mark(mode);
      // Reflect immediately rather than waiting for the next server event.
      // Deliberately NOT gated on state === "IN_TURN": a change made at round
      // end or between rounds used to apply only after a full page reload.
      if (window.SS.repaintUI) window.SS.repaintUI();
    });
  });
})();
